#!/usr/bin/env python3
"""Public free lead feed + provenance-aware community export for Penny Watch NWLA.

Penny Recon publishes machine-readable JSON. Do not confuse national community
reports or reference retail values with verified local store prices.
"""
import csv
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlparse
import pennywatch as pw

ROOT=Path(__file__).resolve().parents[1]
RECON_URL="https://www.pennyrecon.com/data/items.json"
SCHEMA="""
CREATE TABLE IF NOT EXISTS free_community_leads(
  source TEXT NOT NULL, sku TEXT NOT NULL,name TEXT,brand TEXT,
  internet_number TEXT,upc TEXT,retail REAL,reported_at TEXT,
  report_count INTEGER NOT NULL DEFAULT 0,
  source_count INTEGER NOT NULL DEFAULT 1,
  state_counts TEXT NOT NULL DEFAULT '{}',tier TEXT,likelihood TEXT,
  external_score REAL,source_url TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,
  last_imported_at TEXT,PRIMARY KEY(source,sku)
);
CREATE TABLE IF NOT EXISTS free_feed_health(
  source TEXT PRIMARY KEY,method TEXT,status TEXT,checked_at TEXT,
  last_success_at TEXT,row_count INTEGER NOT NULL DEFAULT 0,error TEXT,source_url TEXT
);
CREATE TABLE IF NOT EXISTS free_imports(
  path TEXT PRIMARY KEY,checksum TEXT NOT NULL,imported_at TEXT,
  accepted INTEGER NOT NULL,rejected INTEGER NOT NULL
);
"""
def ensure(cx):
    cx.executescript(SCHEMA)
def utc_now():
    return datetime.now(timezone.utc).isoformat()
def sku(value):
    s=re.sub(r"\D","",str(value or ""))
    if not 3<=len(s)<=18: raise ValueError("invalid SKU")
    return s
def store(value):
    s=str(value or "").zfill(4)
    if s not in pw.STORES:raise ValueError("store not in target list")
    return s
def date(value):
    s=str(value or "")
    if re.fullmatch(r"\d{4}-\d\d-\d\d",s):s+="T00:00:00Z"
    v=datetime.fromisoformat(s.replace("Z","+00:00"))
    if v.tzinfo is None:raise ValueError("missing timezone")
    return v.astimezone(timezone.utc).isoformat()
def https(value,domain=None):
    s=str(value or "").strip()
    u=urlparse(s)
    if u.scheme!="https" or not u.hostname:raise ValueError("HTTPS evidence URL required")
    if domain and u.hostname.lower()!=domain:raise ValueError("unexpected evidence hostname")
    return s
def record_health(cx,name,method,status,count=0,error="",link=""):
    old=cx.execute("SELECT last_success_at FROM free_feed_health WHERE source=?",(name,)).fetchone()
    good=utc_now() if status=="ok" else old[0] if old else None
    cx.execute("INSERT INTO free_feed_health VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(source) DO UPDATE SET "
               "method=excluded.method,status=excluded.status,checked_at=excluded.checked_at,"
               "last_success_at=excluded.last_success_at,row_count=excluded.row_count,"
               "error=excluded.error,source_url=excluded.source_url",
               (name,method,status,utc_now(),good,count,error[:260],link))
def upsert(cx,d):
    fields=("source","sku","name","brand","internet_number","upc","retail","reported_at",
            "report_count","source_count","state_counts","tier","likelihood","external_score",
            "source_url","active","last_imported_at")
    row=dict(d)
    row["state_counts"]=json.dumps(row.get("state_counts") or {},sort_keys=True)
    row["active"]=1
    row["last_imported_at"]=utc_now()
    args=[row.get(k) for k in fields]
    updates=", ".join(k+"=excluded."+k for k in fields[2:])
    sql="INSERT INTO free_community_leads("+",".join(fields)+") VALUES("+",".join("?" for _ in fields)+") "
    cx.execute(sql+"ON CONFLICT(source,sku) DO UPDATE SET "+updates,args)
def normalise_recon(raw):
    if not isinstance(raw,dict):raise ValueError("not a record")
    states=raw.get("states") or {}
    if not isinstance(states,dict):raise ValueError("bad state data")
    states={str(k).upper():int(v) for k,v in states.items() if re.fullmatch("[A-Za-z]{2}",str(k)) and str(v).isdigit() and 0<=int(v)<100000}
    n=int(raw.get("reports") or 0)
    s=int(raw.get("sourceCount") or 1)
    if n<0 or s<0:raise ValueError("invalid report counts")
    retail=raw.get("retail")
    retail=float(retail) if retail is not None else None
    if retail is not None and not 0<=retail<1_000_000:raise ValueError("invalid retail reference")
    return {
       "source":"Penny Recon","sku":sku(raw.get("sku")),
       "name":str(raw.get("name") or "")[:260],"brand":str(raw.get("brand") or "")[:120],
       "internet_number":str(raw.get("internetNumber") or "")[:30],
       "upc":str(raw.get("upc") or "")[:25],"retail":retail,
       "reported_at":date(raw.get("lastSeenAt")),"report_count":n,"source_count":s,
       "state_counts":states,"tier":str(raw.get("tier") or "")[:20],
       "likelihood":str(raw.get("likelihood") or "")[:20],
       "external_score":float(raw.get("score") or 0),
       "source_url":https(raw.get("url"),"www.pennyrecon.com")
    }
def fetch_recon():
    req=Request(RECON_URL,headers={"User-Agent":"PennyWatchNWLA/1.1 (+https://github.com/micahtipton/penny-watch-nwla)","Accept":"application/json"})
    with urlopen(req,timeout=20) as r:
        if r.status!=200:raise ValueError("HTTP "+str(r.status))
        b=r.read(6_000_001)
        if len(b)>6_000_000:raise ValueError("oversized published feed")
    return json.loads(b.decode("utf-8"))
def sync_recon(cx,data=None):
    ensure(cx)
    try:
        if data is None:data=fetch_recon()
        if not isinstance(data,list) or not 1<=len(data)<=5000:
            raise ValueError("unexpected JSON list size or structure")
        items=[];skipped=0
        for raw in data:
            try:items.append(normalise_recon(raw))
            except (TypeError,ValueError,OverflowError):skipped+=1
        if not items or skipped>len(data)*.20:
            raise ValueError("feed schema drift: "+str(skipped)+" invalid records")
        with cx:
            cx.execute("UPDATE free_community_leads SET active=0 WHERE source='Penny Recon'")
            for item in items:upsert(cx,item)
            record_health(cx,"Penny Recon","published JSON","ok",len(items),
                          str(skipped)+" invalid records",RECON_URL)
        return {"status":"ok","accepted":len(items),"rejected":skipped}
    except Exception as exc:
        with cx:record_health(cx,"Penny Recon","published JSON","error",0,
                              type(exc).__name__+": "+str(exc),RECON_URL)
        return {"status":"error","message":str(exc)}
def extend_dashboard(cx,payload):
    ensure(cx)
    leads=[]
    for r in cx.execute("SELECT * FROM free_community_leads WHERE active=1 ORDER BY reported_at DESC"):
        states=json.loads(r["state_counts"] or "{}")
        la=int(states.get("LA",0));near=sum(int(states.get(x,0)) for x in ("TX","AR","MS"))
        priority=round(min(100,max(0,float(r["external_score"] or 0)*.43)+min(28,la*8)+
                           min(18,near*2.5)+min(12,int(r["source_count"] or 0)*3)),1)
        leads.append({
           "source":r["source"],"sku":r["sku"],"name":r["name"],"brand":r["brand"],
           "internet_number":r["internet_number"],"retail_reference":r["retail"],
           "report_count":r["report_count"],"source_count":r["source_count"],
           "state_counts":states,"la_reports":la,"neighbor_reports":near,
           "reported_at":r["reported_at"],"tier":r["tier"],"likelihood":r["likelihood"],
           "priority_score":priority,"source_url":r["source_url"],
           "store_id":None,"store_price":None,"confirmed_local":False
        })
    leads.sort(key=lambda x:(x["priority_score"],x["reported_at"] or ""),reverse=True)
    payload["community_leads"]=leads[:1000]
    payload["community_count"]=len(leads)
    payload["sources_detail"]=[dict(x) for x in cx.execute("SELECT * FROM free_feed_health ORDER BY source")]
    payload["community_updated_at"]=next((x["last_success_at"] for x in payload["sources_detail"] if x["source"]=="Penny Recon"),None)
    target=ROOT/"docs"/"data"/"community-leads.csv"
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("w",encoding="utf-8",newline="") as f:
        w=csv.writer(f)
        w.writerow(["source","sku","name","brand","reported_at","reported_aggregate","reported_sources","LA_reports","nearby_reports","tier","priority_score","source_url"])
        for x in leads:w.writerow([x["source"],x["sku"],x["name"],x["brand"],x["reported_at"],x["report_count"],x["source_count"],x["la_reports"],x["neighbor_reports"],x["tier"],x["priority_score"],x["source_url"]])
    return payload
