"""json_utils 单元测试:围栏感知 JSON 提取与重试。"""
import unittest

from thermolit.json_utils import extract_json


class TestExtractJson(unittest.TestCase):
    def test_fenced_json(self):
        text = '以下是结果:\n```json\n{"a": 1, "b": "x"}\n```'
        self.assertEqual(extract_json(text), {"a": 1, "b": "x"})

    def test_raw_json_with_prose(self):
        text = 'Sure! {"material_system": "Bi2Te3", "zT_value": null} hope that helps'
        self.assertEqual(extract_json(text),
                         {"material_system": "Bi2Te3", "zT_value": None})

    def test_json_array(self):
        self.assertEqual(extract_json('["q1", "q2"]'), ["q1", "q2"])

    def test_array_of_objects_keeps_array_semantics(self):
        # 回归:数组内含对象时,不能被先按大括号截成单个 dict
        text = 'sure:\n[{"statement": "s", "criteria": [{"var": "zT", "op": ">", "value": 1}]}]'
        parsed = extract_json(text)
        self.assertIsInstance(parsed, list)
        self.assertEqual(parsed[0]["criteria"][0]["var"], "zT")

    def test_trailing_comma_tolerated(self):
        self.assertEqual(extract_json('{"a": 1, "b": 2,}'), {"a": 1, "b": 2})

    def test_invalid_returns_none(self):
        self.assertIsNone(extract_json("no json here"))
        self.assertIsNone(extract_json(None))

    def test_old_strip_hack_would_fail_but_new_works(self):
        # 旧实现 .strip("```json") 会把 JSON 内容中的 ` j s o n 字符剥掉导致损坏
        text = '```json\n{"note": "json fence test", "v": 2}\n```'
        self.assertEqual(extract_json(text), {"note": "json fence test", "v": 2})


if __name__ == "__main__":
    unittest.main()
