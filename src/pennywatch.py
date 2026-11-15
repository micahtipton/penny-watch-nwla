#!/usr/bin/env python3
"""Penny Watch NWLA: permitted-source ingestion, append-only SQLite and static Pages export."""
import argparse,csv,hashlib,io,json,os,sqlite3,sys,zipfile
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/'data'/'penny_watch.sqlite'
DOCS=ROOT/'docs'
STORES=('0364','0356','0381')
STORE_LABEL={'0364':'Bossier City','0356':'Bert Kouns','0381':'West Shreveport'}
SOURCE_KEYS=[*(f'CATALOG_FEED_{s}' for s in STORES),*(f'PRICE_FEED_{s}' for s in STORES),*(f'PRIORITY_FEED_{s}' for s in STORES),'REPORTS_FEED_URL','RETAIL_FEED_URL']
SCHEMA="""
CREATE TABLE IF NOT EXISTS products(store TEXT NOT NULL,sku TEXT NOT NULL,name TEXT NOT NULL DEFAULT '',brand TEXT,category TEXT,upc TEXT,product_id TEXT,source_url TEXT,discovered_at TEXT,PRIMARY KEY(store,sku));
CREATE TABLE IF NOT EXISTS observations(id INTEGER PRIMARY KEY,store TEXT,sku TEXT,price REAL,regular_price REAL,price_type TEXT,source TEXT,source_url TEXT,observed_at TEXT,run_id TEXT,identity TEXT UNIQUE);
CREATE INDEX IF NOT EXISTS ix_observations_store_sku ON observations(store,sku,observed_at);
CREATE TABLE IF NOT EXISTS reports(id INTEGER PRIMARY KEY,sku TEXT,title TEXT,state TEXT,city TEXT,source TEXT,source_url TEXT,reported_at TEXT,price REAL,identity TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS offers(id INTEGER PRIMARY KEY,sku TEXT,store TEXT,retailer TEXT,total REAL,source_url TEXT,observed_at TEXT,identity TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,started_at TEXT,status TEXT,observed_by_store TEXT,expected_by_store TEXT,errors TEXT,archive TEXT);
CREATE TABLE IF NOT EXISTS imports(path TEXT PRIMARY KEY,checksum TEXT,imported_at TEXT);
"""
def now():return datetime.now(timezone.utc).isoformat()
def sku(v):
 v=''.join(c for c in str(v or '') if c.isdigit())
 if not 3<=len(v)<=18:raise ValueError('invalid numeric SKU')
 return v
def store(v):
 v=str(v or '').zfill(4)
 if v not in STORES:raise ValueError('unknown store '+v)
 return v
def tm(v):
 val=str(v or '').strip()
 if not val:raise ValueError('missing source observation time')
 from datetime import datetime as dt
 parsed=dt.fromisoformat(val.replace('Z','+00:00'))
 if parsed.tzinfo is None:raise ValueError('source timestamp must include timezone')
 return parsed.astimezone(timezone.utc).isoformat()
def url(v):
 v=str(v or '').strip()
 if not v.startswith('https://') or not urlparse(v).hostname:raise ValueError('https source URL required')
 return v
def ident(*values):return hashlib.sha256(json.dumps(values,ensure_ascii=False).encode()).hexdigest()
def db():
 DB.parent.mkdir(parents=True,exist_ok=True)
 cx=sqlite3.connect(DB)
 cx.row_factory=sqlite3.Row
 cx.executescript(SCHEMA)
 return cx
def rows_for(text):
 text=text.lstrip('\ufeff')
 if text.lstrip().startswith(('[','{')):
  obj=json.loads(text)
  if isinstance(obj,dict):return obj.get('items',[]),obj.get('expected_count')
  return obj,None
 return list(csv.DictReader(io.StringIO(text))),None
def load_url(address,post=None):
 if not address:return [],None
 url(address)
 headers={'User-Agent':'PennyWatchNWLA/1.0 (authorized-source collector)','Accept':'application/json,text/csv'}
 bearer=os.environ.get('AUTH_FEED_BEARER','')
 if bearer:headers['Authorization']='Bearer '+bearer
 body=json.dumps(post).encode() if post is not None else None
 if body:headers['Content-Type']='application/json'
 request=Request(address,data=body,headers=headers,method='POST' if post is not None else 'GET')
 with urlopen(request,timeout=25) as r:
  if r.status!=200:raise ValueError('feed HTTP '+str(r.status))
  data=r.read(12_000_001)
  if len(data)>12_000_000:raise ValueError('feed exceeds 12 MB safety limit')
 return rows_for(data.decode('utf-8'))
def item_product(cx,x,force_store=None):
 st=store(force_store or x.get('store_id') or x.get('store'))
 sk=sku(x.get('sku'))
 cx.execute('INSERT INTO products(store,sku,name,brand,category,upc,product_id,source_url,discovered_at) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(store,sku) DO UPDATE SET name=CASE WHEN excluded.name!="" THEN excluded.name ELSE products.name END,brand=COALESCE(excluded.brand,products.brand),category=COALESCE(excluded.category,products.category),source_url=COALESCE(excluded.source_url,products.source_url)',
 (st,sk,str(x.get('name') or ''),x.get('brand'),x.get('category'),x.get('upc'),x.get('product_id'),x.get('source_url'),now()))
 return st,sk
def price(cx,x,run,force_store=None):
 st,sk=item_product(cx,x,force_store)
 amount=float(x['price'])
 if not 0<=amount<1_000_000:raise ValueError('invalid price')
 reg=x.get('regular_price');reg=float(reg) if reg not in ('',None) else None
 if reg is not None and not 0<reg<1_000_000:raise ValueError('invalid regular price')
 ty=str(x.get('price_type') or 'unknown')
 if ty not in ('online','clearance','shelf','pos','unknown'):raise ValueError('invalid price type')
 source_url=url(x.get('source_url'))
 observed=tm(x.get('observed_at'))
 src=str(x.get('source') or 'Authorized feed')
 key=ident(st,sk,amount,reg,ty,src,source_url,observed)
 cur=cx.execute('INSERT OR IGNORE INTO observations(store,sku,price,regular_price,price_type,source,source_url,observed_at,run_id,identity) VALUES(?,?,?,?,?,?,?,?,?,?)',(st,sk,amount,reg,ty,src,source_url,observed,run,key))
 return st,sk,cur.rowcount
def report(cx,x):
 sk=sku(x.get('sku'));link=url(x.get('source_url'));when=tm(x.get('reported_at') or x.get('observed_at'))
 priceval=float(x['price']) if x.get('price') not in (None,'') else None
 v=(sk,str(x.get('title') or ''),str(x.get('state') or '').upper(),str(x.get('city') or ''),str(x.get('source') or 'Community'),link,when,priceval)
 return cx.execute('INSERT OR IGNORE INTO reports(sku,title,state,city,source,source_url,reported_at,price,identity) VALUES(?,?,?,?,?,?,?,?,?)',(*v,ident(*v))).rowcount
def offer(cx,x):
 st=store(x.get('store_id') or x.get('store'));sk=sku(x.get('sku'));link=url(x.get('source_url'))
 total=float(x['total']);when=tm(x.get('observed_at'));retailer=str(x.get('retailer') or '')
 if total<0 or not retailer:raise ValueError('invalid retailer comparison')
 v=(sk,st,retailer,total,link,when)
 return cx.execute('INSERT OR IGNORE INTO offers(sku,store,retailer,total,source_url,observed_at,identity) VALUES(?,?,?,?,?,?,?)',(*v,ident(*v))).rowcount
def import_items(cx,kind,items,run_id,store_id=None):
 count=0
 for row in items:
  try:
   if kind=='catalog':item_product(cx,row,store_id);count+=1
   elif kind=='prices':count+=price(cx,row,run_id,store_id)[2]
   elif kind=='reports':count+=report(cx,row)
   elif kind=='comparisons':count+=offer(cx,row)
  except (ValueError,TypeError,KeyError) as e:
   print('Invalid sourced record:',str(e),file=sys.stderr)
 return count
def import_files(cx,run):
 amounts=defaultdict(int)
 folder=ROOT/'imports'
 folder.mkdir(exist_ok=True)
 for p in sorted(folder.glob('*.csv')):
  kind=next((x for x in ('catalog','prices','reports','comparisons') if p.name.startswith(x+'-')),None)
  if not kind:continue
  digest=hashlib.sha256(p.read_bytes()).hexdigest()
  prev=cx.execute('SELECT checksum FROM imports WHERE path=?',(p.name,)).fetchone()
  if prev and prev[0]==digest:continue
  items,_=rows_for(p.read_text(encoding='utf-8-sig'))
  amounts[kind]+=import_items(cx,kind,items,run)
  cx.execute('INSERT OR REPLACE INTO imports(path,checksum,imported_at) VALUES(?,?,?)',(p.name,digest,now()))
 return dict(amounts)
def snapshot(cx,run):
 out=DOCS/'exports';out.mkdir(parents=True,exist_ok=True)
 path=out/(run+'.zip')
 result=cx.execute('SELECT store,sku,price,regular_price,price_type,source,source_url,observed_at FROM observations WHERE run_id=? ORDER BY store,sku',(run,)).fetchall()
 data=io.StringIO();writer=csv.writer(data)
 writer.writerow(['store_id','sku','price','regular_price','price_type','source','source_url','observed_at'])
 for row in result:writer.writerow(list(row))
 with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as z:z.writestr('price-observations.csv',data.getvalue())
 return 'exports/'+path.name
def collect(run):
 cx=db();timestamp=now();counts={s:0 for s in STORES};expected={};errors=[];configured=any(os.environ.get(f'PRICE_FEED_{s}') for s in STORES)
 for st in STORES:
  for kind,key in [('catalog',f'CATALOG_FEED_{st}'),('prices',f'PRICE_FEED_{st}')]:
   link=os.environ.get(key,'')
   if not link:continue
   try:
    data,n=load_url(link)
    count=import_items(cx,kind,data,run,st)
    if kind=='prices':counts[st]+=count
    if n is not None and kind=='prices':expected[st]=int(n)
   except Exception as e:errors.append(f'{key}: {type(e).__name__} {str(e)[:130]}')
 for kind,key in [('reports','REPORTS_FEED_URL'),('comparisons','RETAIL_FEED_URL')]:
  if os.environ.get(key):
   try:items,_=load_url(os.environ[key]);import_items(cx,kind,items,run)
   except Exception as e:errors.append(f'{key}: {type(e).__name__} {str(e)[:130]}')
 import_files(cx,run)
 # Public community feed supplies leads, never store-specific prices.
 try:
  import free_sources as fs
  fs.ensure(cx)
  if os.environ.get('PW_FETCH_PENNYRECON','1')!='0':
   feed_result=fs.sync_recon(cx)
   print('Community feed: '+json.dumps(feed_result))
 except ModuleNotFoundError:
  pass  # Keep the standalone collector valid without optional free-source module.
 except Exception as e:
  errors.append('community integration: '+str(e)[:140])
 # Bounded three-store online storefront check. Stops on HTTP refusal.
 try:
  import hd_live
  hd_live_result=hd_live.scan(cx,run)
  print('HD ONLINE PRICE CHECK: '+json.dumps(hd_live_result))
  if hd_live_result['status'] in ('partial','cooldown','no_price_data'):
   statuses={st:info.get('status','unknown') for st,info in hd_live_result.get('stores',{}).items()}
   errors.append('Home Depot store check '+hd_live_result['status']+'; '+json.dumps(statuses,sort_keys=True))
 except ModuleNotFoundError:
  pass
 except Exception as e:
  errors.append('Home Depot check: '+type(e).__name__+': '+str(e)[:130])
 # Source exports require exact local SKU, store, timestamp and evidence URL.
 try:
  import source_imports
  import_result=source_imports.import_exports(cx,run)
  if import_result:print('Imported source exports: '+json.dumps(import_result))
 except ModuleNotFoundError:
  pass  # Manual exports module is optional in minimal deployments.
 except Exception as e:
  errors.append('source imports: '+str(e)[:140])
 # Count saved observations, including source imports (not just direct feeds).
 counts={st:cx.execute('SELECT COUNT(*) FROM observations WHERE run_id=? AND store=?',(run,st)).fetchone()[0] for st in STORES}
 if sum(counts.values())>0:configured=True
 archive=snapshot(cx,run)
 total=sum(counts.values())
 # One SKU observed in earlier runs does not count as sampled this run.
 status=('partial' if errors else 'source_unconfigured' if not configured else 'no_prices' if total==0 else
         'partial_unknown_coverage' if any(st not in expected or counts[st]<expected[st] for st in STORES) else 'complete_tracked_scope')
 cx.execute('INSERT OR REPLACE INTO runs VALUES(?,?,?,?,?,?,?)',(run,timestamp,status,json.dumps(counts),json.dumps(expected),'; '.join(errors),archive))
 cx.commit();cx.close()
 print(json.dumps({'run':run,'status':status,'saved_by_store':counts,'expected':expected,'errors':errors,'archive':archive}))
def writecsv(path,heads,records):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('w',newline='',encoding='utf-8') as f:
  w=csv.writer(f);w.writerow(heads);w.writerows(records)
def build():
 cx=db();(DOCS/'data').mkdir(parents=True,exist_ok=True)
 products=cx.execute('SELECT * FROM products ORDER BY store,sku').fetchall()
 observations=cx.execute('SELECT * FROM observations ORDER BY observed_at').fetchall()
 bykey=defaultdict(list)
 for o in observations:bykey[(o['store'],o['sku'])].append(dict(o))
 reports=defaultdict(list)
 for r in cx.execute('SELECT * FROM reports ORDER BY reported_at DESC'):reports[r['sku']].append(dict(r))
 offers=defaultdict(list)
 for o in cx.execute('SELECT * FROM offers ORDER BY observed_at DESC'):offers[(o['store'],o['sku'])].append(dict(o))
 leads=[]
 for product in products:
  st,sk=product['store'],product['sku'];series=bykey[(st,sk)]
  if not series:continue
  last=series[-1];current=float(last['price'])
  baselines=[float(o['regular_price']) for o in series if o['regular_price'] is not None and o['regular_price']>0]
  baselines += [float(o['price']) for o in series]
  baseline=max(baselines) if baselines else None
  # A single first observation without sourced regular price has no defensible discount.
  if len(series)==1 and last['regular_price'] is None:baseline=None
  pct=round((baseline-current)/baseline*100,1) if baseline and baseline>=current else None
  rs=reports.get(sk,[]);region=sum(1 for o in rs if o['state'] in ('LA','TX','AR','MS'))
  sources=len(set(o['source']+'|'+o['source_url'] for o in rs))
  score=min(100,round((pct or 0)*.45+min(30,region*8)+min(20,sources*7)))
  conf='Low - community lead' if rs else 'Observed online only'
  rec=dict(store_id=st,sku=sk,name=product['name'] or sk,price=current,drop_pct=pct,score=score,confidence=conf,source_url=last['source_url'],report_count=len(rs),report_sources=sources,source_reports=rs[:4],offers=offers.get((st,sk),[])[:3])
  leads.append(rec)
 leads.sort(key=lambda r:r['score'],reverse=True)
 clearance=[x for x in leads if x['drop_pct'] is not None and x['drop_pct']>0]
 clearance.sort(key=lambda x:x['drop_pct'],reverse=True)
 monday=sorted(leads,key=lambda x:(STORES.index(x['store_id']),-x['score']))[:150]
 runs=[]
 for x in cx.execute('SELECT * FROM runs ORDER BY started_at DESC LIMIT 100'):
  r=dict(x);r['observed_by_store']=json.loads(r['observed_by_store']);r['expected_by_store']=json.loads(r['expected_by_store']);runs.append(r)
 counts={s:cx.execute('SELECT COUNT(*) FROM products WHERE store=?',(s,)).fetchone()[0] for s in STORES}
 payload={'tracked_count':sum(counts.values()),'observation_count':len(observations),'counts':counts,'runs':runs,'sources':{k:bool(os.environ.get(k)) for k in SOURCE_KEYS},'leads':leads[:500],'clearance':clearance[:500],'monday':monday}
 try:
  import free_sources as fs
  fs.extend_dashboard(cx,payload)
  try:
   import hd_live
   hd_live.init(cx)
   payload['hd_scan_checks']=[dict(row) for row in cx.execute('SELECT * FROM hd_check_history ORDER BY checked_at DESC LIMIT 60')]
   payload['hd_stock']=[dict(row) for row in cx.execute('SELECT * FROM hd_stock_observations ORDER BY checked_at DESC LIMIT 500')]
  except ModuleNotFoundError:
   pass
 except Exception as e:
  payload['free_sources_error']=str(e)[:240]
 (DOCS/'data'/'dashboard.json').write_text(json.dumps(payload,ensure_ascii=False,default=str))
 writecsv(DOCS/'data'/'current-prices.csv',['store','sku','name','price','drop_pct','source'],[(x['store_id'],x['sku'],x['name'],x['price'],x['drop_pct'],x['source_url']) for x in leads])
 writecsv(DOCS/'data'/'penny-leads.csv',['store','sku','name','price','confidence','reports','source'],[(x['store_id'],x['sku'],x['name'],x['price'],x['confidence'],x['report_count'],x['source_url']) for x in leads if x['report_count']])
 writecsv(DOCS/'data'/'monday-checklist.csv',['store','sku','name','price','drop_pct','priority','source'],[(x['store_id'],x['sku'],x['name'],x['price'],x['drop_pct'],x['score'],x['source_url']) for x in monday])
 buckets=defaultdict(list)
 for o in observations:
  sk=o['sku'];bucket=sum(map(ord,sk))%128
  buckets[bucket].append(dict(store_id=o['store'],sku=sk,price=o['price'],regular_price=o['regular_price'],price_type=o['price_type'],observed_at=o['observed_at'],source=o['source'],source_url=o['source_url'],run_id=o['run_id']))
 import shutil
 hd=DOCS/'history'
 if hd.exists():shutil.rmtree(hd)
 hd.mkdir(exist_ok=True)
 for bucket,records in buckets.items():(hd/('bucket-'+str(bucket).zfill(3)+'.json')).write_text(json.dumps(records))
 print('Built dashboard:',len(leads),'products with observed prices,',len(runs),'runs')
 cx.close()
def main():
 p=argparse.ArgumentParser();p.add_argument('command',choices=['init','collect','build','monday']);p.add_argument('--slot')
 a=p.parse_args()
 if a.command=='init':db().close();print('Initialized database')
 elif a.command=='collect':collect(a.slot or datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
 elif a.command=='monday':build()
 else:build()
if __name__=='__main__':main()
