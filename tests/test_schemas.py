"""Pydantic 抽取契约测试。"""
import unittest

from thermolit.schemas import validate_extraction


class TestValidateExtraction(unittest.TestCase):
    def test_valid_record(self):
        data = {"material_system": "Bi2Te3", "seebeck_coefficient": "-180 uV/K",
                "temperature_k": 350,
                "evidence_sentences": {"seebeck_coefficient":
                                       "S = -180 uV/K was measured at 350 K."}}
        normalized, err = validate_extraction(data)
        self.assertIsNone(err)
        self.assertEqual(normalized["material_system"], "Bi2Te3")
        self.assertEqual(normalized["evidence_sentences"]["seebeck_coefficient"],
                         "S = -180 uV/K was measured at 350 K.")
        # 未提供的字段规范化为 None(下游统一处理)
        self.assertIsNone(normalized["zT_value"])
        self.assertIsNone(normalized["electrical_conductivity"])

    def test_numeric_string_temperature_coerced(self):
        normalized, err = validate_extraction({"temperature_k": "350"})
        self.assertIsNone(err)
        self.assertEqual(normalized["temperature_k"], 350.0)

    def test_invalid_temperature_reports_field(self):
        normalized, err = validate_extraction({"temperature_k": "room temperature"})
        self.assertIsNone(normalized)
        self.assertIn("temperature_k", err)

    def test_non_dict_rejected(self):
        normalized, err = validate_extraction(["not", "a", "dict"])
        self.assertIsNone(normalized)
        self.assertIn("JSON 对象", err)

    def test_extra_keys_ignored(self):
        normalized, err = validate_extraction({"material_system": "PbTe",
                                               "hallucinated_field": "x"})
        self.assertIsNone(err)
        self.assertNotIn("hallucinated_field", normalized)

    def test_null_fields_pass(self):
        normalized, err = validate_extraction({"material_system": None,
                                               "zT_value": None})
        self.assertIsNone(err)
        self.assertEqual(normalized["evidence_sentences"], {})


if __name__ == "__main__":
    unittest.main()
