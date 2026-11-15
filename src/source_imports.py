#!/usr/bin/env python3
"""Imports supplied CSV/JSON exports from free sources; no scraping performed."""
import csv,hashlib,io,json,sqlite3
from pathlib import Path
import pennywatch as pw
import free_sources as fs
ROOT=Path(__file__).resolve().parents[1]
KNOWN={"2scraper","hdscanner","omkar","pennycentral","pennyloot"}
def value(r,*keys):
    for k in keys:
        x=r.get(k)
        if x is not None and str(x).strip()!="":return x
    return None
def rows(path):
    txt=path.read_text(encoding="utf-8-sig")
    if txt.lstrip().startswith(("[","{")):
        d=json.loads(txt)
        return d if isinstance(d,list) else d.get("items",d.get("data",[]))
    return list(csv.DictReader(io.StringIO(txt)))
def row_import(cx,source,row,run):
    if not isinstance(row,dict):raise ValueError("not an object")
    if source in ("2scraper","hdscanner","omkar"):
        st=fs.store(value(row,"store_id","storeId","store"))
        if source=="2scraper":
            sk=fs.sku(value(row,"store_sku","storeSku"))
            internet=value(row,"sku","product_id")
        elif source=="omkar":
            sk=fs.sku(value(row,"store_sku","storeSku"))
            internet=value(row,"id","product_id")
        else:
            sk=fs.sku(value(row,"store_sku","storeSku","sku"))
            internet=value(row,"product_id","internet_number")
        observed=fs.date(value(row,"observed_at","scraped_at","collected_at","timestamp"))
        source_url=fs.https(value(row,"source_url","url","product_url","link"))
        amount=value(row,"price","current_price","sale_price")
        if amount is None:raise ValueError("missing price")
        pw.price(cx,{
            "store_id":st,"sku":sk,"name":value(row,"name","title") or "",
            "brand":value(row,"brand") or "",
            "category":value(row,"category") or "",
            "product_id":str(internet or ""),"price":amount,
            "regular_price":value(row,"regular_price","original_price"),
            "price_type":"online","source":source+" supplied export",
            "source_url":source_url,"observed_at":observed
        },run)
    else:
        domain="www.pennycentral.com" if source=="pennycentral" else "www.pennyloot.com"
        sk=fs.sku(value(row,"sku","store_sku"))
        link=fs.https(value(row,"source_url","url","link"),domain=domain)
        observed=fs.date(value(row,"observed_at","reported_at","timestamp"))
        state=str(value(row,"state") or "").upper()
        fs.upsert(cx,{
            "source":"PennyCentral manual" if source=="pennycentral" else "PennyLoot manual",
            "sku":sk,"name":str(value(row,"name","title") or "")[:260],
            "brand":str(value(row,"brand") or "")[:120],
            "internet_number":"","upc":str(value(row,"upc") or ""),"retail":None,
            "reported_at":observed,"report_count":1,"source_count":1,
            "state_counts":{state:1} if len(state)==2 and state.isalpha() else {},
            "tier":"unverified","likelihood":"unverified",
            "external_score":0,"source_url":link
        })
def import_exports(cx,run="free-sources"):
    fs.ensure(cx)
    folder=ROOT/"imports"
    folder.mkdir(exist_ok=True)
    out=[]
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.suffix.lower() not in (".csv",".json"):continue
        source=path.name.lower().split("-",1)[0]
        if source not in KNOWN:continue
        checksum=hashlib.sha256(path.read_bytes()).hexdigest()
        old=cx.execute("SELECT checksum FROM free_imports WHERE path=?",(path.name,)).fetchone()
        if old and old[0]==checksum:continue
        accepted=0;rejected=0
        try:
            data=rows(path)
            if not isinstance(data,list) or len(data)>100000:raise ValueError("invalid source export")
            with cx:
                for item in data:
                    try:
                        with cx:row_import(cx,source,item,run)
                        accepted+=1
                    except (ValueError,KeyError,TypeError,OverflowError,sqlite3.Error):
                        rejected+=1
                cx.execute("INSERT OR REPLACE INTO free_imports VALUES(?,?,?,?,?)",
                    (path.name,checksum,fs.utc_now(),accepted,rejected))
                fs.record_health(cx,source,"user-provided export",
                    "ok" if not rejected else "partial",accepted,
                    str(rejected)+" rejected rows",str(path.relative_to(ROOT)))
        except Exception as err:
            fs.record_health(cx,source,"user-provided export","error",0,
                str(err),str(path.relative_to(ROOT)))
            rejected+=1
        out.append({"file":path.name,"source":source,"accepted":accepted,"rejected":rejected})
    cx.commit()
    return out
