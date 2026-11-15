import sqlite3,sys,unittest
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
 def test_refusal_stops_other_stores_and_sets_cooldown(self):
  c=db()
  calls=[]
  def blocked(st,key):
   calls.append(st)
   raise hd.RemoteRefusal('403 denied')
  output=hd.scan(c,'test-refused',requester=blocked)
  self.assertEqual(output['status'],'refused')
  self.assertEqual(calls,['0364'])
  self.assertEqual(c.execute("SELECT COUNT(*) FROM hd_cooldown").fetchone()[0],1)
  c.close()
 def test_missing_valid_store_sku_not_saved(self):
  broken=model()
  broken['products'][0]['identifiers']['storeSkuNumber']=None
  self.assertEqual(hd.normalize_products(broken,'0364','2026-11-15T05:00:00+00:00'),[])
if __name__=='__main__':unittest.main()
