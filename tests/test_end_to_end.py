"""Offline end-to-end check of the independent three-store pipeline."""
import csv,json,os,sqlite3,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import pennywatch as pw
import hd_live,free_sources,source_imports

def sample_product(store):
 return {"products":[{"itemId":"300000008","identifiers":{
 "storeSkuNumber":"1004455667","productLabel":"Synthetic fixture garden tool",
 "brandName":"Fixture","canonicalUrl":"/p/fixture/300000008"},
 "pricing":{"value":7.50,"original":25.0},
 "fulfillment":{"fulfillmentOptions":[{"services":[{"locations":[{"locationId":store,
 "inventory":{"quantity":3,"isInStock":True}}]}]}]}}]}
def sample_community():
 return [{"sku":"1009024891","name":"Synthetic report","brand":"Fixture",
 "internetNumber":"321000007","upc":"098765432109","retail":39.99,
 "lastSeenAt":"2026-11-14T12:30:00Z","reports":3,"sourceCount":2,
 "states":{"LA":1,"TX":2},"tier":"reported","likelihood":"medium",
 "score":20,"url":"https://www.pennyrecon.com/item/1009024891/"}]
class PipelineTest(unittest.TestCase):
 def test_independent_collection_through_archive_and_dashboard(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/"imports").mkdir()
   docs=root/"docs";dbfile=root/"data"/"penny_watch.sqlite"
   calls=[]
   def stub(store,term):
    calls.append((store,term));return sample_product(store)
   with patch.object(pw,"ROOT",root),patch.object(pw,"DB",dbfile),\
        patch.object(pw,"DOCS",docs),patch.object(free_sources,"ROOT",root),\
        patch.object(source_imports,"ROOT",root),patch.object(hd_live,"request",stub),\
        patch.object(free_sources,"fetch_recon",sample_community),\
        patch.dict(os.environ,{"PW_HD_ENABLED":"1","PW_HD_MAX_QUERIES":"3","PW_FETCH_PENNYRECON":"1"}):
    pw.collect("e2e-test")
    pw.build()
    p=json.loads((docs/"data"/"dashboard.json").read_text())
    self.assertEqual(len(calls),3)
    self.assertEqual({s for s,t in calls},set(pw.STORES))
    self.assertEqual(p["observation_count"],3)
    self.assertEqual(p["tracked_count"],3)
    self.assertEqual(p["community_count"],1)
    self.assertEqual(p["runs"][0]["status"],"partial_unknown_coverage")
    self.assertEqual(p["runs"][0]["observed_by_store"],{"0364":1,"0356":1,"0381":1})
    self.assertEqual(len(p["hd_stock"]),3)
    self.assertEqual({r["store_id"] for r in p["leads"]},set(pw.STORES))
    self.assertEqual({r["drop_pct"] for r in p["leads"]},{70.0})
    self.assertIsNone(p["community_leads"][0]["store_price"])
    for name in ("current-prices.csv","penny-leads.csv","monday-checklist.csv","community-leads.csv"):
     self.assertTrue((docs/"data"/name).is_file(),name)
    with zipfile.ZipFile(docs/"exports/e2e-test.zip") as archive:
     records=list(csv.DictReader(archive.read("price-observations.csv").decode().splitlines()))
    self.assertEqual(len(records),3)
    self.assertEqual({r["store_id"] for r in records},set(pw.STORES))
    with sqlite3.connect(dbfile) as db:
     self.assertEqual(db.execute("SELECT COUNT(*) FROM observations").fetchone()[0],3)
 def test_no_old_arklatex_site_dependency(self):
  self.assertNotIn("arklatex",source_imports.KNOWN)
if __name__=="__main__":unittest.main()
