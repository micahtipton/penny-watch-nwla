#!/usr/bin/env python3
"""Bounded, non-evasive Home Depot price-check pilot for three Louisiana stores.

Uses the standard Home Depot storefront GraphQL response shape documented in
MIT-licensed HDScanner: https://github.com/KenStager/HDScanner
No proxies, browser impersonation, challenge-solving, credentials, retry storms,
or rate-limit workarounds. HTTP 206 is inspected, not automatically cooled down.
Results are ONLINE prices scoped to a requested store, not confirmed POS prices.
"""
from __future__ import annotations
import json,os,re,subprocess,time,sqlite3
from datetime import datetime,timezone,timedelta
from urllib.parse import urlparse
import pennywatch as pw

ENDPOINT="https://apionline.homedepot.com/federation-gateway/graphql?opname=searchModel"
QUERY="""query searchModel($storeId:String,$startIndex:Int,$pageSize:Int,$orderBy:ProductSort,$filter:ProductFilter,$isBrandPricingPolicyCompliant:Boolean,$keyword:String,$navParam:String,$storefilter:StoreFilter=ALL,$channel:Channel=DESKTOP,$additionalSearchParams:AdditionalParams){searchModel(keyword:$keyword,navParam:$navParam,storefilter:$storefilter,isBrandPricingPolicyCompliant:$isBrandPricingPolicyCompliant,storeId:$storeId,channel:$channel,additionalSearchParams:$additionalSearchParams){searchReport{totalProducts}products(startIndex:$startIndex,pageSize:$pageSize,orderBy:$orderBy,filter:$filter){itemId identifiers{brandName modelNumber canonicalUrl productLabel storeSkuNumber itemId upc productType}pricing(storeId:$storeId,isBrandPricingPolicyCompliant:$isBrandPricingPolicyCompliant){value original promotion{type dollarOff percentageOff promotionTag savingsCenter}specialBuy clearance{value dollarOff percentageOff}}fulfillment{fulfillmentOptions{type services{type locations{inventory{isOutOfStock isInStock isLimitedQuantity quantity}isAnchor locationId storeName type}}}}availabilityType{type discontinued buyable status}}}}"""
KEYWORDS=("Husky","Ryobi","Milwaukee","Glacier Bay","Hampton Bay","HDX","Home Decorators Collection","DeWalt","Commercial Electric","Defiant","Everbilt","Westinghouse")
SCHEMA="""
CREATE TABLE IF NOT EXISTS hd_check_history(
 run_id TEXT,store TEXT,attempted INTEGER,valid_responses INTEGER,
 product_rows INTEGER,price_rows INTEGER,stock_rows INTEGER,
 status TEXT,reason TEXT,checked_at TEXT,PRIMARY KEY(run_id,store)
);
CREATE TABLE IF NOT EXISTS hd_stock_observations(
 store TEXT,sku TEXT,product_id TEXT,quantity INTEGER,stock_status TEXT,
 checked_at TEXT,run_id TEXT,PRIMARY KEY(run_id,store,sku)
);
CREATE TABLE IF NOT EXISTS hd_scan_cursor(
 key TEXT PRIMARY KEY,pos INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS hd_cooldown(
 key TEXT PRIMARY KEY,until_utc TEXT NOT NULL,reason TEXT
);
"""
class RemoteRefusal(RuntimeError):
 def __init__(self,message,kind="refused",retry_after_seconds=None):
  super().__init__(message)
  self.kind=kind
  self.retry_after_seconds=retry_after_seconds
class InvalidResponse(RuntimeError):pass
class PartialContent(InvalidResponse):pass

def init(cx):
 cx.executescript(SCHEMA)
def now():return datetime.now(timezone.utc).isoformat()
def query_variables(store,keyword):
 if store not in pw.STORES:raise ValueError("Unrecognized store")
 if not keyword or len(keyword)>75:raise ValueError("Unsafe or empty keyword")
 return {"storeId":store,"startIndex":0,"pageSize":24,"orderBy":{"field":"BEST_MATCH","order":"ASC"},
 "filter":{},"isBrandPricingPolicyCompliant":False,"keyword":keyword,"navParam":None,
 "storefilter":"IN_STORE","channel":"DESKTOP","additionalSearchParams":{"deliveryZip":"","multiStoreIds":[]}}
def parsed_headers(header_text):
 """Read only safe metadata from the last HTTP response, never credentials."""
 blocks=str(header_text or "").replace("\r","").split("\n\n")
 final=next((b for b in reversed(blocks) if b.lstrip().startswith("HTTP/")),"")
 result={}
 for line in final.splitlines():
  name,sep,value=line.partition(":")
  name=name.strip().lower()
  if sep and name in ("content-type","content-range","retry-after"):
   result[name]=value.strip()[:90]
 return result

def response_diagnostics(header_text,body):
 """Safe HTTP metadata; no response body, tokens or arbitrary headers in logs."""
 headers=parsed_headers(header_text)
 kind=("empty" if not body.strip() else "html" if body.lstrip().startswith("<") else
       "json" if body.lstrip().startswith(("{","[")) else "other")
 def clean(value):
  return re.sub(r"[^A-Za-z0-9_ .,:;=/+-]","",value)[:70]
 return ("body="+kind+", bytes="+str(len(body.encode("utf-8")))+
         ", type="+clean(headers.get("content-type","absent"))+
         ", range="+clean(headers.get("content-range","absent"))+
         ", retry_after="+clean(headers.get("retry-after","absent")))

def retry_after_seconds(value):
 """Respect Retry-After seconds or a real HTTP-date, when supplied."""
 if not value:return None
 try:
  number=float(value)
  if 0<=number<=365*86400:return max(1,int(number))
 except (TypeError,ValueError,OverflowError):pass
 try:
  from email.utils import parsedate_to_datetime
  when=parsedate_to_datetime(value)
  if when.tzinfo is None:when=when.replace(tzinfo=timezone.utc)
  delta=(when-datetime.now(timezone.utc)).total_seconds()
  if delta>=0:return max(1,int(delta)+1)
 except (ValueError,TypeError,IndexError,OverflowError):pass
 return None

def parse_product_response(status,headers_text,body):
 """Classify responses before deciding to stop a store or accept records."""
 headers=parsed_headers(headers_text)
 diag=response_diagnostics(headers_text,body)
 seconds=retry_after_seconds(headers.get("retry-after"))
 if status==429:
  raise RemoteRefusal("HTTP 429 rate limit; "+diag,kind="rate_limited",
                      retry_after_seconds=seconds if seconds is not None else 7200)
 if status in (401,403):
  raise RemoteRefusal("HTTP "+str(status)+" access refusal; "+diag,kind="refused",
                      retry_after_seconds=43200)
 if status==503 and seconds is not None:
  raise RemoteRefusal("HTTP 503 with explicit Retry-After; "+diag,
                      kind="rate_limited",retry_after_seconds=seconds)
 if status not in (200,206):
  raise InvalidResponse("Unexpected HTTP "+str(status)+"; "+diag)
 stripped=body.lstrip()
 if stripped.startswith("<"):
  indicators=("captcha","access denied","verify you are human","are you a robot",
              "unusual traffic","request blocked","akamai","bot detection")
  blocked=any(tag in stripped[:2000].lower() for tag in indicators)
  if blocked:
   raise RemoteRefusal("HTML access challenge; HTTP "+str(status)+"; "+diag,
                       kind="refused",retry_after_seconds=43200)
  raise InvalidResponse("Unexpected HTML instead of JSON; HTTP "+str(status)+"; "+diag)
 if not stripped:
  raise PartialContent("Empty response; HTTP "+str(status)+"; "+diag)
 try:raw=json.loads(body)
 except (ValueError,TypeError):
  raise PartialContent("Incomplete or malformed JSON; HTTP "+str(status)+"; "+diag)
 if not isinstance(raw,dict):
  raise InvalidResponse("Non-object JSON; HTTP "+str(status)+"; "+diag)
 if raw.get("errors") or raw.get("error"):
  raise InvalidResponse("GraphQL error response; HTTP "+str(status)+"; "+diag)
 data=raw.get("data")
 model=data.get("searchModel") if isinstance(data,dict) else None
 if not isinstance(model,dict) or not isinstance(model.get("products"),list):
  raise PartialContent("Missing products array; HTTP "+str(status)+"; "+diag)
 if status==206:
  # Retain valid records, but always flag HTTP 206 as incomplete coverage.
  model["_partial_http"]=True
  model["_http_diagnostic"]=diag
 return model

def request(store,keyword):
 payload=json.dumps({"operationName":"searchModel","query":QUERY,"variables":query_variables(store,keyword)})
 command=["curl","--silent","--show-error","--compressed","--max-time","18",
  "--max-filesize","750000","--dump-header","/dev/stderr","-w","\n%{http_code}","-X","POST","--url",ENDPOINT,
  "-H","Accept: application/json","-H","Content-Type: application/json",
  "-H","Referer: https://www.homedepot.com/","-H","x-experience-name: general-merchandise",
  "-H","x-hd-dc: origin","-H","x-debug: false",
  "-H","User-Agent: PennyWatchNWLA/1.3 (bounded personal research; github.com/micahtipton/penny-watch-nwla)",
  "-d",payload]
 try:res=subprocess.run(command,capture_output=True,text=True,timeout=22)
 except (OSError,subprocess.TimeoutExpired) as err:
  raise InvalidResponse("Connection failure: "+type(err).__name__)
 if res.returncode!=0:
  raise InvalidResponse("HTTP client error (curl exit "+str(res.returncode)+")")
 body,sep,code=res.stdout.rpartition("\n")
 if not sep:raise InvalidResponse("Missing HTTP status line")
 try:status=int(code.strip())
 except ValueError:raise InvalidResponse("Unreadable HTTP status line")
 return parse_product_response(status,res.stderr,body)

def safe_url(identifiers,item_id):
 link=str(identifiers.get("canonicalUrl") or "").strip()
 if link.startswith("/p/"):link="https://www.homedepot.com"+link
 if not link.startswith("https://www.homedepot.com/p/"):
  link="https://www.homedepot.com/p/"+str(item_id)
 parse=urlparse(link)
 if parse.netloc!="www.homedepot.com" or not parse.path.startswith("/p/"):
  link="https://www.homedepot.com/p/"+str(item_id)
 return link
def stock_for(product,store):
 fulfillment=product.get("fulfillment") or {}
 found=[]
 for option in fulfillment.get("fulfillmentOptions") or []:
  for svc in option.get("services") or []:
   for loc in svc.get("locations") or []:
    if str(loc.get("locationId") or "").lstrip("0")==str(store).lstrip("0"):
     inventory=loc.get("inventory") or {}
     # Only record inventory when a fulfillment location is this actual store.
     quantity=inventory.get("quantity")
     try:quantity=int(quantity) if quantity is not None else None
     except (ValueError,TypeError):quantity=None
     status=("in_stock" if inventory.get("isInStock") else
             "out_of_stock" if inventory.get("isOutOfStock") else
             "limited" if inventory.get("isLimitedQuantity") else "unknown")
     found.append((quantity,status))
 return found[0] if found else (None,"not_verified")
def normalize_products(model,store,stamp):
 products=model.get("products") or []
 result=[]
 for item in products:
  if not isinstance(item,dict):continue
  ids=item.get("identifiers") or {}
  rawsku=str(ids.get("storeSkuNumber") or "").strip()
  if not re.fullmatch(r"\d{3,18}",rawsku):continue
  product_id=str(item.get("itemId") or "").strip()
  if not re.fullmatch(r"\d{6,12}",product_id):continue
  pricing=item.get("pricing") or {}
  try:price=float(pricing["value"])
  except (KeyError,TypeError,ValueError):continue
  if not 0<=price<=100000:continue
  original=pricing.get("original")
  try:original=float(original) if original is not None else None
  except (ValueError,TypeError):original=None
  if original is not None and original<price:original=None
  qty,stock=stock_for(item,store)
  result.append({
   "store_id":store,"sku":rawsku,"name":str(ids.get("productLabel") or "")[:240],
   "brand":str(ids.get("brandName") or "")[:100],"product_id":product_id,
   "price":price,"regular_price":original,"source_url":safe_url(ids,product_id),
   "observed_at":stamp,"price_type":"online","source":"Home Depot online storefront (store "+store+")",
   "quantity":qty,"stock_status":stock
  })
 return result
def next_keywords(cx,count):
 row=cx.execute("SELECT pos FROM hd_scan_cursor WHERE key='keywords'").fetchone()
 start=int(row[0]) if row else 0
 keys=[KEYWORDS[(start+i)%len(KEYWORDS)] for i in range(count)]
 cx.execute("INSERT OR REPLACE INTO hd_scan_cursor VALUES('keywords',?)",((start+count)%len(KEYWORDS),))
 return keys
def lead_queries(cx,per_store):
 # Use source's exact SKU, not the internet item number, for search.
 try:
  rows=cx.execute("SELECT sku FROM free_community_leads WHERE active=1 AND "
                  "(CAST(json_extract(state_counts,'$.LA') AS INTEGER)>0 OR "
                  " CAST(json_extract(state_counts,'$.TX') AS INTEGER)>0 OR "
                  " CAST(json_extract(state_counts,'$.AR') AS INTEGER)>0) "
                  "ORDER BY reported_at DESC LIMIT 40").fetchall()
  if not rows:return []
  cursor=cx.execute("SELECT pos FROM hd_scan_cursor WHERE key='leads'").fetchone()
  pos=int(cursor[0]) if cursor else 0
  selected=[rows[(pos+i)%len(rows)][0] for i in range(min(per_store,len(rows)))]
  cx.execute("INSERT OR REPLACE INTO hd_scan_cursor VALUES('leads',?)",((pos+len(selected))%len(rows),))
  return selected
 except sqlite3.Error:return []
def scan(cx,run_id,requester=None):
 init(cx); requester=requester or request
 selected=(os.environ.get("PW_HD_ENABLED","1")!="0")
 if not selected:return {"status":"disabled","saved":0,"stores":{}}
 cooldown=cx.execute("SELECT until_utc,reason FROM hd_cooldown WHERE key='global'").fetchone()
 if cooldown:
  try:until=datetime.fromisoformat(cooldown[0])
  except ValueError:until=datetime.now(timezone.utc)
  if until>datetime.now(timezone.utc):
   return {"status":"cooldown","saved":0,"reason":cooldown[1],"stores":{}}
 budget=min(12,max(3,int(os.environ.get("PW_HD_MAX_QUERIES","9"))))
 per_store=max(1,budget//3)
 brands=next_keywords(cx,max(1,per_store-1))
 targeted=lead_queries(cx,1) if per_store>1 else []
 combos=(brands+targeted)[:per_store]
 results={};refused=False;seen=set();total=0
 for st in pw.STORES:
  attempted=0;valid=0;products=0;saved=0;stock_n=0;messages=[]
  for key in combos:
   if refused:break
   attempted+=1
   try:response=requester(st,key)
   except RemoteRefusal as exc:
    refused=True;messages.append(str(exc));break
   except Exception as exc:
    messages.append(type(exc).__name__+": "+str(exc)[:110]);continue
   valid+=1
   rows=normalize_products(response,st,now());products+=len(rows)
   for row in rows:
    # One product per store per run, regardless of keyword duplicates.
    ident=(st,row["sku"])
    if ident in seen:continue
    seen.add(ident)
    try:
     inserted=pw.price(cx,row,run_id)[2]
     saved+=inserted;total+=inserted
     cx.execute("INSERT OR REPLACE INTO hd_stock_observations VALUES(?,?,?,?,?,?,?)",
       (st,row["sku"],row["product_id"],row["quantity"],row["stock_status"],row["observed_at"],run_id))
     stock_n+=int(row["stock_status"]!="not_verified")
    except (ValueError,KeyError,TypeError,sqlite3.Error) as exc:
     messages.append("invalid sourced product "+str(exc)[:50])
   # No retry and no concurrent requests. Be gentle.
   if requester is request:time.sleep(1.4)
  status=("refused" if refused else "ok_partial_scope" if saved else
          "no_prices" if valid else "error")
  info={"attempted":attempted,"valid_responses":valid,"product_rows":products,
        "price_rows":saved,"stock_rows":stock_n,"status":status,"reason":"; ".join(messages)[:250]}
  results[st]=info
  cx.execute("INSERT OR REPLACE INTO hd_check_history VALUES(?,?,?,?,?,?,?,?,?,?)",
     (run_id,st,attempted,valid,products,saved,stock_n,status,info["reason"],now()))
  try:
   import free_sources
   free_sources.record_health(cx,"Home Depot "+st,"online storefront query",status,saved,info["reason"],ENDPOINT)
  except (ImportError,sqlite3.Error):pass
  if refused:
   until=(datetime.now(timezone.utc)+timedelta(hours=24)).isoformat()
   cx.execute("INSERT OR REPLACE INTO hd_cooldown VALUES('global',?,?)",(until,"access refusal on "+st))
   break
 cx.commit()
 return {"status":"refused" if refused else "partial_scope" if total else "no_price_data",
         "saved":total,"stores":results,"queries":combos}
