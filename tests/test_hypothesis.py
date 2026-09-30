"""假说回验引擎测试:派生变量、确定性判定、LLM 输出归一化。"""
import unittest

from thermolit.hypothesis import (
    CANONICAL_VARS,
    derive_variables,
    evaluate_hypotheses,
    missing_to_gap_queries,
    normalize_experiment_plan,
    normalize_hypotheses,
)


class TestDeriveVariables(unittest.TestCase):
    def test_power_factor(self):
        m = derive_variables({"S": 200e-6, "sigma": 1e5})
        self.assertAlmostEqual(m["PF"], 200e-6 ** 2 * 1e5, places=12)

    def test_zT_derivation_clean_numbers(self):
        m = derive_variables({"S": 200e-6, "sigma": 1e5, "T_K": 300.0, "kappa": 1.5})
        self.assertAlmostEqual(m["zT"], 0.8, places=6)

    def test_kappa_split(self):
        m = derive_variables({"kappa": 1.3, "kappa_e": 0.7})
        self.assertAlmostEqual(m["kappa_l"], 0.6)
        m2 = derive_variables({"kappa": 1.3, "kappa_l": 0.6})
        self.assertAlmostEqual(m2["kappa_e"], 0.7)

    def test_kappa_l_via_wiedemann_franz(self):
        # 回验侧与审计引擎同源:S=-2.4e-4, σ=8.5e4, T=350, κ=1.05
        # → κ_e = L(240µV/K)·σ·T ≈ 0.491,κ_l ≈ 0.559
        m = derive_variables({"S": -2.4e-4, "sigma": 8.5e4, "kappa": 1.05, "T_K": 350})
        self.assertAlmostEqual(m["kappa_e"], 1.65e-8 * 8.5e4 * 350, places=6)
        self.assertAlmostEqual(m["kappa_l"], 1.05 - 1.65e-8 * 8.5e4 * 350, places=6)

    def test_ignores_unknown_keys(self):
        m = derive_variables({"S": 1e-4, "bogus": 3})
        self.assertNotIn("bogus", m)


class TestEvaluateHypotheses(unittest.TestCase):
    HYP_ZT = [{"id": "H1", "statement": "zT >= 0.79",
               "criteria": [{"var": "zT", "op": ">=", "value": 0.79}]}]

    def test_supported(self):
        # S=200e-6, sigma=1e5, T=300, kappa=1.5 → zT ≈ 0.8
        # 判据取 0.79:避开浮点边界(精确压在 0.8 上会因 FP 误差翻转)
        ev = evaluate_hypotheses(self.HYP_ZT,
                                 {"S": 200e-6, "sigma": 1e5, "T_K": 300, "kappa": 1.5})
        self.assertEqual(ev[0]["status"], "supported")
        self.assertEqual(ev[0]["missing"], [])

    def test_refuted(self):
        ev = evaluate_hypotheses(
            [{"id": "H1", "criteria": [{"var": "zT", "op": ">", "value": 0.9}]}],
            {"S": 200e-6, "sigma": 1e5, "T_K": 300, "kappa": 1.5})
        self.assertEqual(ev[0]["status"], "refuted")
        self.assertAlmostEqual(ev[0]["criteria_results"][0]["measured"], 0.8, places=6)

    def test_inconclusive_with_missing_reflux(self):
        ev = evaluate_hypotheses(
            [{"id": "H1", "criteria": [{"var": "kappa_l", "op": "<", "value": 0.3}]}],
            {"zT": 0.9})
        self.assertEqual(ev[0]["status"], "inconclusive")
        self.assertTrue(any("kappa_l" in m for m in ev[0]["missing"]))

    def test_temperature_condition_mismatch(self):
        ev = evaluate_hypotheses(
            [{"id": "H1", "criteria": [{"var": "S", "op": "<", "value": -1e-4,
                                        "T_K": 400}]}],
            {"S": -1.8e-4, "T_K": 350})
        self.assertEqual(ev[0]["status"], "inconclusive")
        self.assertTrue(any("温度不符" in m for m in ev[0]["missing"]))

    def test_temperature_condition_within_tolerance(self):
        ev = evaluate_hypotheses(
            [{"id": "H1", "criteria": [{"var": "S", "op": "<", "value": -1e-4,
                                        "T_K": 355}]}],
            {"S": -1.8e-4, "T_K": 350})
        self.assertEqual(ev[0]["status"], "supported")


class TestNormalizeHypotheses(unittest.TestCase):
    def test_valid_hypothesis_passes(self):
        hyps, warns = normalize_hypotheses([
            {"statement": "kappa_l < 0.3 at 400K",
             "criteria": [{"var": "kappa_l", "op": "<", "value": 0.3, "T_K": 400}],
             "evidence_dois": ["10.1/a"], "rationale": "nanostructuring"}],
            known_dois={"10.1/a"})
        self.assertEqual(len(hyps), 1)
        self.assertEqual(warns, [])
        self.assertNotIn("unverified_dois", hyps[0])
        self.assertEqual(hyps[0]["criteria"][0]["T_K"], 400.0)

    def test_unknown_variable_dropped_with_warning(self):
        hyps, warns = normalize_hypotheses([
            {"statement": "s", "criteria": [{"var": "magic", "op": "<", "value": 1}]}])
        self.assertEqual(hyps, [])
        self.assertTrue(any("magic" in w for w in warns))

    def test_non_numeric_threshold_rejected(self):
        hyps, warns = normalize_hypotheses([
            {"statement": "s", "criteria": [{"var": "zT", "op": ">", "value": "high"}]}])
        self.assertEqual(hyps, [])
        self.assertTrue(any("不是数值" in w for w in warns))

    def test_unverified_doi_tagged(self):
        hyps, warns = normalize_hypotheses([
            {"statement": "s", "criteria": [{"var": "zT", "op": ">", "value": 1}],
             "evidence_dois": ["10.1/known", "10.1/bogus"]}],
            known_dois={"10.1/known"})
        self.assertEqual(hyps[0]["unverified_dois"], ["10.1/bogus"])
        self.assertTrue(any("10.1/bogus" in w for w in warns))

    def test_max_n_cap(self):
        raw = [{"statement": f"s{i}", "criteria": [{"var": "zT", "op": ">", "value": 1}]}
               for i in range(8)]
        hyps, _ = normalize_hypotheses(raw, max_n=5)
        self.assertEqual(len(hyps), 5)

    def test_canonical_vars_cover_measurement_language(self):
        for var in ("S", "sigma", "kappa_l", "zT", "PF", "T_K"):
            self.assertIn(var, CANONICAL_VARS)


class TestNormalizeExperimentPlan(unittest.TestCase):
    HYPS = [{"id": "H1", "statement": "s", "criteria": []}]

    def test_valid_plan(self):
        plan, warns = normalize_experiment_plan({
            "summary": "s", "samples": ["Bi2Te3 x=0.01", "Bi2Te3 x=0.03"],
            "measurements": [{"target_var": "kappa_l", "technique": "laser flash",
                              "T_range_K": [300, "500"]}],
            "hypothesis_refs": ["H1"]}, self.HYPS)
        self.assertEqual(len(plan["measurements"]), 1)
        self.assertEqual(plan["measurements"][0]["T_range_K"], [300.0, 500.0])
        self.assertEqual(warns, [])

    def test_unknown_hypothesis_ref_flagged(self):
        plan, warns = normalize_experiment_plan({
            "measurements": [], "hypothesis_refs": ["H1", "H9"]}, self.HYPS)
        self.assertEqual(plan["hypothesis_refs"], ["H1"])
        self.assertTrue(any("H9" in w for w in warns))

    def test_bad_target_var_dropped(self):
        plan, warns = normalize_experiment_plan({
            "measurements": [{"target_var": "dream", "technique": "x"}]}, self.HYPS)
        self.assertEqual(plan["measurements"], [])
        self.assertTrue(any("dream" in w for w in warns))


class TestMissingToGapQueries(unittest.TestCase):
    def test_missing_vars_map_to_field_queries(self):
        evals = [{"missing": ["missing:kappa_l", "missing:T_K(判据要求 400 K)"]}]
        queries = missing_to_gap_queries(evals, {"thermal_conductivity":
                                                 "total thermal conductivity measurement"})
        self.assertEqual(queries, ["total thermal conductivity measurement"])


if __name__ == "__main__":
    unittest.main()
