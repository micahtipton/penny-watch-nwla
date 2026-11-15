import json
import sqlite3
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
import pennywatch as pw
import free_sources as free
import source_imports as imp

SAMPLE={
 "sku":"1009074829","name":"Example vacuum","brand":"Example",
 "internetNumber":"323830662","upc":"0033287212446","retail":199,
 "lastSeenAt":"2026-11-12T20:23:08.983Z","reports":238,
 "states":{"LA":1,"TX":22,"AR":0,"MS":0},
 "sourceCount":1,"tier":"hot","likelihood":"high","score":134.5,
 "url":"https://www.pennyrecon.com/item/1009074829/"
}
def database():
 c=sqlite3.connect(":memory:")
 c.row_factory=sqlite3.Row
 c.executescript(pw.SCHEMA)
 free.ensure(c)
 return c
class FeedTests(unittest.TestCase):
 def test_recon_published_schema_and_no_store_price(self):
  c=database()
  result=free.sync_recon(c,[SAMPLE])
  self.assertEqual(result["status"],"ok")
  p={}
  free.extend_dashboard(c,p)
  self.assertEqual(p["community_count"],1)
  lead=p["community_leads"][0]
  self.assertEqual(lead["sku"],"1009074829")
  self.assertIsNone(lead["store_id"])
  self.assertIsNone(lead["store_price"])
  self.assertFalse(lead["confirmed_local"])
  self.assertGreater(lead["priority_score"],0)
  self.assertEqual(c.execute("SELECT COUNT(*) FROM observations").fetchone()[0],0)
  c.close()
 def test_failed_new_feed_does_not_erase_old_leads(self):
  c=database()
  self.assertEqual(free.sync_recon(c,[SAMPLE])["status"],"ok")
  result=free.sync_recon(c,{"changed":"schema"})
  self.assertEqual(result["status"],"error")
  self.assertEqual(c.execute("SELECT COUNT(*) FROM free_community_leads WHERE active=1").fetchone()[0],1)
  self.assertEqual(c.execute("SELECT status FROM free_feed_health WHERE source='Penny Recon'").fetchone()[0],"error")
  c.close()
 def test_2scraper_internet_id_is_not_store_sku(self):
  c=database()
  row={
    "store_id":"364","sku":"321488310","store_sku":"1008223977",
    "title":"Saw","price":"649.0",
    "scraped_at":"2026-09-22T11:56:20.360165+00:00",
    "url":"https://www.homedepot.com/p/product/321488310"
  }
  imp.row_import(c,"2scraper",row,"r1")
  self.assertEqual(c.execute("SELECT sku,store,price FROM observations").fetchone()[:],
                   ("1008223977","0364",649.0))
  self.assertEqual(c.execute("SELECT COUNT(*) FROM observations WHERE sku='321488310'").fetchone()[0],0)
  c.close()
 def test_non_target_store_rejected(self):
  c=database()
  row={
    "store_id":"121","sku":"321488310","store_sku":"1008223977",
    "price":649,"scraped_at":"2026-09-22T11:56:20+00:00",
    "url":"https://www.homedepot.com/p/321488310"
  }
  with self.assertRaises(ValueError):imp.row_import(c,"2scraper",row,"r1")
  self.assertEqual(c.execute("SELECT COUNT(*) FROM observations").fetchone()[0],0)
  c.close()
 def test_ambiguous_product_id_rejected(self):
  c=database()
  row={
    "store_id":"0364","sku":"321488310",
    "price":649,"scraped_at":"2026-09-22T11:56:20+00:00",
    "url":"https://www.homedepot.com/p/321488310"
  }
  with self.assertRaises(ValueError):imp.row_import(c,"2scraper",row,"r1")
  c.close()
if __name__=="__main__":unittest.main()
