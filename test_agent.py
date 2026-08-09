import unittest
import os
import json
from sciverse_adapter import SciverseAdapter

class TestThermoLitAgent(unittest.TestCase):
    def setUp(self):
        self.adapter = SciverseAdapter()

    def test_sciverse_search(self):
        print("\n[Test] Testing Sciverse API Search Connection...")
        results = self.adapter.search_sync("Bi2Te3 thermoelectric", top_k=2)
        self.assertIsInstance(results, list)
        if len(results) > 0:
            print(f"[Test PASS] Retrived {len(results)} hits. First title: {results[0].get('title')}")
            self.assertIn("title", results[0])
            self.assertIn("doi", results[0])
        else:
            print("[Test WARNING] No hits returned (Check network or API token)")

    def test_json_records_structure(self):
        data_path = "../阶段一_基本任务提交/data/deepresearch_all_records.json"
        if os.path.exists(data_path):
            print(f"\n[Test] Auditing output JSON structure at {data_path}...")
            with open(data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertIn("all_records", data)
            self.assertIn("metrics", data)
            print(f"[Test PASS] JSON contains {len(data['all_records'])} literature records.")

if __name__ == "__main__":
    unittest.main()
