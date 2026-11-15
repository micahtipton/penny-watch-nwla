import sqlite3,sys,unittest
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import pennywatch as pw
import free_sources as fs
import hd_live as hd

def db():
 c=sqlite3.connect(':memory:')
 c.row_factory=sqlite3.Row
 c.executescript(pw.SCHEMA)
 fs.ensure(c)
 hd.init(c)
 return c

def model(store='0364'):
 return {'products':[{
  'itemId':'300000008','identifiers':{'storeSkuNumber':'1004455667','productLabel':'Example garden tool','brandName':'TestBrand','canonicalUrl':'/p/example/300000008'},
  'pricing':{'value':7.50,'original':25.0,'clearance':{'value':7.50}},
  'fulfillment':{'fulfillmentOptions':[{'services':[{'locations':[{'locationId':store,'inventory':{'quantity':3,'isInStock':True}}]}]}]}
 }],'searchReport':{'totalProducts':1}}
class HomeDepotCheckTests(unittest.TestCase):
 def test_normalized_price_stays_in_queried_store(self):
  result=hd.normalize_products(model(),'0364','2026-11-15T05:00:00+00:00')
  self.assertEqual(len(result),1)
  self.assertEqual(result[0]['store_id'],'0364')
  self.assertEqual(result[0]['sku'],'1004455667')
  self.assertEqual(result[0]['quantity'],3)
  self.assertEqual(result[0]['price_type'],'online')
 def test_never_assume_stock_at_different_location(self):
  result=hd.normalize_products(model('0356'),'0364','2026-11-15T05:00:00+00:00')
  self.assertEqual(result[0]['stock_status'],'not_verified')
  self.assertIsNone(result[0]['quantity'])
 def test_requester_pilot_is_bounded_and_uses_three_stores(self):
  c=db()
  calls=[]
  def fake(st,key):
   calls.append((st,key))
   return model(st)
  import os
  old=os.environ.get('PW_HD_MAX_QUERIES')
  os.environ['PW_HD_MAX_QUERIES']='3'
  try:
   output=hd.scan(c,'test-store-scan',requester=fake)
   self.assertEqual(output['saved'],3)
   self.assertEqual(set(st for st,key in calls),set(pw.STORES))
   self.assertEqual(len(calls),3)
   self.assertEqual(c.execute('SELECT COUNT(*) FROM observations').fetchone()[0],3)
  finally:
   if old is None:os.environ.pop('PW_HD_MAX_QUERIES',None)
   else:os.environ['PW_HD_MAX_QUERIES']=old
  c.close()
 def test_refusal_pauses_only_affected_store(self):
  c=db()
  calls=[]
  def refused_first(st,key):
   calls.append(st)
   if st=='0364':
    raise hd.RemoteRefusal('HTTP 403',kind='refused',retry_after_seconds=43200)
   return model(st)
  import os
  with patch.dict(os.environ,{'PW_HD_MAX_QUERIES':'3'}):
   output=hd.scan(c,'test-refused',requester=refused_first)
  self.assertEqual(output['status'],'partial')
  self.assertEqual(calls,list(pw.STORES))
  self.assertEqual(c.execute("SELECT key FROM hd_cooldown").fetchone()[0],'store:0364')
  self.assertEqual(output['saved'],2)
  self.assertEqual(output['stores']['0364']['status'],'refused')
  self.assertEqual(output['stores']['0356']['status'],'ok_partial_scope')
  c.close()
 def test_http_206_with_valid_json_is_partial_not_a_refusal(self):
  c=db()
  calls=[]
  def partial_first(st,key):
   calls.append(st)
   out=model(st)
   if st=='0364':out['_partial_http']=True
   return out
  import os
  with patch.dict(os.environ,{'PW_HD_MAX_QUERIES':'3'}):
   output=hd.scan(c,'test-206-valid',requester=partial_first)
  self.assertEqual(output['status'],'partial')
  self.assertEqual(output['saved'],3)
  self.assertEqual(output['stores']['0364']['status'],'partial_response')
  self.assertEqual(c.execute("SELECT COUNT(*) FROM hd_cooldown").fetchone()[0],0)
  self.assertEqual(calls,list(pw.STORES))
  c.close()
 def test_http_206_malformed_json_continues_to_other_stores(self):
  c=db()
  calls=[]
  def bad_first(st,key):
   calls.append(st)
   if st=='0364':
    return hd.parse_product_response(206,'HTTP/2 206\\r\\ncontent-range: bytes 0-5/100\\r\\n\\r\\n','{"broken"')
   return model(st)
  import os
  with patch.dict(os.environ,{'PW_HD_MAX_QUERIES':'3'}):
   output=hd.scan(c,'test-206-malformed',requester=bad_first)
  self.assertEqual(output['status'],'partial')
  self.assertEqual(output['saved'],2)
  self.assertEqual(output['stores']['0364']['status'],'partial_response')
  self.assertEqual(c.execute("SELECT COUNT(*) FROM hd_cooldown").fetchone()[0],0)
  self.assertEqual(calls,list(pw.STORES))
  c.close()
 def test_429_retry_after_stops_only_that_store(self):
  c=db()
  def one_limited(st,key):
   if st=='0356':
    return hd.parse_product_response(429,'HTTP/2 429\\r\\nretry-after: 1800\\r\\n\\r\\n','')
   return model(st)
  import os
  with patch.dict(os.environ,{'PW_HD_MAX_QUERIES':'3'}):
   output=hd.scan(c,'test-rate',requester=one_limited)
  self.assertEqual(output['saved'],2)
  self.assertEqual(output['stores']['0356']['status'],'rate_limited')
  self.assertEqual(c.execute("SELECT key FROM hd_cooldown").fetchone()[0],'store:0356')
  self.assertEqual(output['stores']['0381']['status'],'ok_partial_scope')
  c.close()
 def test_old_global_cooldown_is_cleared(self):
  c=db()
  c.execute("INSERT INTO hd_cooldown VALUES('global','2999-01-01T00:00:00+00:00','old 206')")
  import os
  with patch.dict(os.environ,{'PW_HD_MAX_QUERIES':'3'}):
   output=hd.scan(c,'test-legacy-block',requester=lambda st,key:model(st))
  self.assertEqual(output['saved'],3)
  self.assertEqual(c.execute("SELECT COUNT(*) FROM hd_cooldown").fetchone()[0],0)
  c.close()
 def test_206_response_classification_and_genuine_refusal(self):
  valid=__import__('json').dumps({'data':{'searchModel':model()}})
  accepted=hd.parse_product_response(206,'HTTP/2 206\\r\\ncontent-type: application/json\\r\\n\\r\\n',valid)
  self.assertEqual(accepted['products'][0]['itemId'],'300000008')
  self.assertTrue(accepted['_partial_http'])
  with self.assertRaises(hd.PartialContent):
   hd.parse_product_response(206,'HTTP/2 206\\r\\n\\r\\n','{"incomplete"')
  with self.assertRaises(hd.RemoteRefusal) as ctx:
   hd.parse_product_response(206,'HTTP/2 206\\r\\n\\r\\n','<html>Verify you are human</html>')
  self.assertEqual(ctx.exception.kind,'refused')
 def test_graphql_application_error_is_not_automatically_a_block(self):
  import json
  message=json.dumps({'errors':[{'message':'Unknown argument in schema',
                                'extensions':{'code':'GRAPHQL_VALIDATION_FAILED'}}]})
  with self.assertRaises(hd.InvalidResponse) as x:
   hd.parse_product_response(206,'HTTP/2 206\r\ncontent-type: application/json\r\n\r\n',message)
  self.assertNotIsInstance(x.exception,hd.RemoteRefusal)
  self.assertIn("code=GRAPHQL_VALIDATION_FAILED",str(x.exception))
  self.assertIn("message_class=schema_or_query",str(x.exception))
 def test_generic_gateway_error_identified_without_leaking_payload(self):
  import json
  payload={"errors":[{"message":"Generic Errors API","extensions":{"code":"UNKNOWN"}}],"data":None}
  raw=json.dumps(payload)
  with self.assertRaises(hd.GatewayError) as ctx:
   hd.parse_product_response(206,"HTTP/2 206\r\ncontent-type: application/json\r\n\r\n",raw)
  output=str(ctx.exception)
  self.assertIn("generic gateway error",output)
  self.assertIn("message_class=generic_error",output)
  self.assertIn("payload_hash=",output)
  self.assertNotIn("Generic Errors API",output)
  self.assertNotIn(raw,output)
 def test_generic_error_does_not_disable_other_stores(self):
  import json,os
  c=db()
  calls=[]
  def responder(st,key):
   calls.append(st)
   if st=="0364":
    payload={"errors":[{"message":"Generic Errors API"}]}
    return hd.parse_product_response(206,"HTTP/2 206\r\n\r\n",json.dumps(payload))
   return model(st)
  with patch.dict(os.environ,{"PW_HD_MAX_QUERIES":"3"}):
   output=hd.scan(c,"test-generic",requester=responder)
  self.assertEqual(calls,list(pw.STORES))
  self.assertEqual(output["saved"],2)
  self.assertEqual(output["stores"]["0364"]["status"],"gateway_error")
  self.assertEqual(c.execute("SELECT COUNT(*) FROM hd_cooldown").fetchone()[0],0)
  c.close()
 def test_graphql_explicit_rate_limit_honors_retry_after(self):
  import json
  msg=json.dumps({'errors':[{'message':'Too many requests','extensions':{'code':'RATE_LIMITED'}}]})
  with self.assertRaises(hd.RemoteRefusal) as x:
   hd.parse_product_response(206,'HTTP/2 206\r\nretry-after: 120\r\n\r\n',msg)
  self.assertEqual(x.exception.kind,'rate_limited')
  self.assertEqual(x.exception.retry_after_seconds,120)
 def test_graphql_explicit_access_denial_is_a_refusal(self):
  import json
  msg=json.dumps({'errors':[{'message':'Access denied','extensions':{'code':'FORBIDDEN'}}]})
  with self.assertRaises(hd.RemoteRefusal) as x:
   hd.parse_product_response(206,'HTTP/2 206\r\n\r\n',msg)
  self.assertEqual(x.exception.kind,'refused')
 def test_http_403_retry_after_is_honored(self):
  with self.assertRaises(hd.RemoteRefusal) as x:
   hd.parse_product_response(403,'HTTP/2 403\r\nretry-after: 900\r\n\r\n','')
  self.assertEqual(x.exception.retry_after_seconds,900)
 def test_http_206_diagnostics_are_metadata_only(self):
  headers=("HTTP/2 206\r\ncontent-type: application/json\r\n"
           "content-range: bytes 0-19/100\r\nretry-after: 120\r\n"
           "set-cookie: SECRET=123\r\n\r\n")
  result=hd.response_diagnostics(headers,'{"error":"limited"}')
  self.assertIn("range=bytes 0-19/100",result)
  self.assertIn("retry_after=120",result)
  self.assertNotIn("SECRET",result)
  self.assertNotIn("limited",result)
 def test_missing_valid_store_sku_not_saved(self):
  broken=model()
  broken['products'][0]['identifiers']['storeSkuNumber']=None
  self.assertEqual(hd.normalize_products(broken,'0364','2026-11-15T05:00:00+00:00'),[])
if __name__=='__main__':unittest.main()
