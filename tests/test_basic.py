import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]

class SmokeTests(unittest.TestCase):
    def test_empty_scan_never_claims_full_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'src').mkdir()
            (root/'src'/'pennywatch.py').write_bytes((SOURCE/'src'/'pennywatch.py').read_bytes())
            for args in [('init',),('collect','--slot','test-empty'),('build',)]:
                p=subprocess.run([sys.executable,'src/pennywatch.py',*args],cwd=root,capture_output=True,text=True,timeout=20)
                self.assertEqual(p.returncode,0,p.stdout+'\n'+p.stderr)
            dashboard=json.loads((root/'docs/data/dashboard.json').read_text())
            self.assertEqual(dashboard['observation_count'],0)
            self.assertEqual(dashboard['runs'][0]['status'],'source_unconfigured')
            self.assertEqual(sum(dashboard['runs'][0]['observed_by_store'].values()),0)
            archive=root/'docs/exports/test-empty.zip'
            self.assertTrue(archive.exists())
            with zipfile.ZipFile(archive) as z:
                rows=z.read('price-observations.csv').decode().splitlines()
                self.assertEqual(len(rows),1)
    def test_exact_store_and_sku_validation(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('pw',SOURCE/'src/pennywatch.py')
        import types
        pw=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pw)
        self.assertEqual(pw.store('364'),'0364')
        self.assertEqual(pw.sku('100-200-300'),'100200300')
        with self.assertRaises(ValueError):pw.store('9999')
        with self.assertRaises(ValueError):pw.sku('not a sku')

if __name__=='__main__':unittest.main()
