"""Contract and behaviour tests for the packaging analysis."""
import unittest
from pathlib import Path

import numpy as np

from analysis import core
from analysis.corrections import correction_impact, evidence_review
from analysis.identifiability import (
    attribute_isolation,
    copy_cell_alias,
    copy_shape_verdict,
    design_identifiability,
    position_confound,
)
from analysis.modeling import design_rates, effect_table, fit_suite
from analysis.policy import applicable_policy, design_policy_matrix, template_recommendation
from analysis.submissions import evaluate_template, submission_context
from analysis.templates import plate_accounting, template_compatibility
from analysis.validation import leave_one_design_out

DATA = Path("data")


class AuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = core.load(DATA)

    def test_one_sided_trials_are_not_none(self):
        audit = core.trial_audit(self.bundle)
        self.assertEqual(audit["one_sided_early_termination"], 21)
        self.assertEqual(audit["one_sided_coded_none"], 0)
        self.assertEqual(audit["two_sided"], 363)

    def test_choice_rows_exclude_one_sided(self):
        rows = core.choices(self.bundle)
        self.assertEqual(len(rows), 363)
        self.assertTrue(all(r.left is not None and r.right is not None for r in rows))
        self.assertEqual(sum(1 for r in rows if r.choice == 2), 34)

    def test_correction_resolution_by_day(self):
        # All trials predate the correction, so displayed d5 has the old emphasis.
        day = min(t["day"] for t in self.bundle.trials)
        self.assertEqual(self.bundle.displayed_spec("d5", day).emphasis, "突出")
        self.assertEqual(self.bundle.corrected_spec("d5").emphasis, "普通")


class IdentifiabilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = core.load(DATA)

    def test_copy_and_cells_are_aliased(self):
        verdict = copy_cell_alias(self.bundle)
        self.assertTrue(verdict["aliased"])
        self.assertFalse(copy_shape_verdict(self.bundle)["copy_separable_from_cells"])

    def test_copy_is_separable_from_shape(self):
        # The no-copy version appears on 圆 and 长, so copy is not a shape proxy.
        verdict = copy_shape_verdict(self.bundle)
        self.assertTrue(verdict["copy_separable_from_shape"])
        self.assertEqual(sorted(verdict["no_copy_shapes"]), ["圆", "长"])

    def test_pair_rank_below_design_rank(self):
        ident = design_identifiability(self.bundle)
        self.assertLess(ident["corrected"]["pair_rank"], ident["corrected"]["design_rank"])

    def test_only_one_pair_isolates_a_single_layout_attribute(self):
        iso = attribute_isolation(self.bundle)["single_attribute_pairs"]
        self.assertEqual(iso["order"], 1)
        self.assertEqual(iso["emphasis"], 0)

    def test_position_is_fixed_within_block(self):
        pos = position_confound(self.bundle)
        self.assertTrue(pos["position_fixed_within_block"])
        self.assertEqual(pos["crossed_designs"], ["d8"])


class ModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = core.load(DATA)
        cls.suite = fit_suite(cls.bundle)

    def test_rank_matches_parameters(self):
        for key in ("choice", "meaning", "hce"):
            fit_ = self.suite[key]
            self.assertEqual(fit_.hessian_rank, len(fit_.beta))

    def test_order_is_the_meaning_effect(self):
        fit_ = self.suite["meaning"]
        row = {r["term"]: r for r in effect_table(fit_, self.suite["coder"])}
        self.assertGreater(row["order=成分先"]["coef"], 0)
        self.assertLess(row["order=成分先"]["p"], 0.01)
        # emphasis is not distinguishable from zero
        self.assertGreater(row["emph=突出"]["p"], 0.1)

    def test_order_reduces_high_confidence_error(self):
        fit_ = self.suite["hce"]
        row = {r["term"]: r for r in effect_table(fit_, self.suite["coder"])}
        self.assertLess(row["order=成分先"]["coef"], 0)
        self.assertLess(row["order=成分先"]["p"], 0.01)

    def test_choice_attributes_are_indistinguishable(self):
        fit_ = self.suite["choice"]
        row = {r["term"]: r for r in effect_table(fit_, self.suite["coder"])}
        for term in ("order=成分先", "emph=突出", "copy=无说明"):
            self.assertGreater(row[term]["p"], 0.1)

    def test_leave_one_design_out_is_bounded(self):
        rows = leave_one_design_out(self.bundle)
        self.assertEqual(len(rows), 8)
        for row in rows:
            self.assertGreaterEqual(row["meaning_predicted"], 0.0)
            self.assertLessEqual(row["meaning_predicted"], 1.0)
            self.assertLess(abs(row["meaning_error"]), 0.25)


class PolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = core.load(DATA)

    def test_named_group_floor_overrides_product_floor(self):
        policy = applicable_policy(self.bundle, "a", "普通读者")
        # product a floor 0.74, group floor 0.72 -> stricter 0.74
        self.assertAlmostEqual(policy["min_understanding"], 0.74)
        policy_old = applicable_policy(self.bundle, "a", "老读者")
        self.assertAlmostEqual(policy_old["min_understanding"], 0.74)

    def test_t1_masks_product_a_breach_behind_product_b(self):
        matrix = design_policy_matrix(self.bundle)
        d1 = next(r for r in matrix["rates"] if r["design"] == "d1" and r["group"] == "ALL")
        d4 = next(r for r in matrix["rates"] if r["design"] == "d4" and r["group"] == "ALL")
        self.assertFalse(d1["pass"])
        self.assertTrue(d4["pass"])
        pooled = (d1["misunderstanding"] * d1["n"] + d4["misunderstanding"] * d4["n"]) / (d1["n"] + d4["n"])
        self.assertLess(pooled, 0.24)
        self.assertGreater(pooled, 0.21)


class TemplateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = core.load(DATA)

    def test_t1_is_internally_compatible_but_must_split(self):
        compat = {r["template"]["template"]: r for r in template_compatibility(self.bundle)}
        self.assertTrue(compat["t1"]["compatible"])
        rec = {r["template"]["template"]: r for r in template_recommendation(self.bundle)}
        self.assertEqual(rec["t1"]["verdict"], "split")

    def test_t2_declares_incompatible_copy(self):
        compat = {r["template"]["template"]: r for r in template_compatibility(self.bundle)}
        self.assertFalse(compat["t2"]["compatible"])
        rec = {r["template"]["template"]: r for r in template_recommendation(self.bundle)}
        self.assertEqual(rec["t2"]["verdict"], "rebuild_and_split")

    def test_signed_template_is_review_not_retest(self):
        rec = {r["template"]["template"]: r for r in template_recommendation(self.bundle)}
        self.assertEqual(rec["t4"]["verdict"], "signed_review")
        self.assertFalse(rec["t4"]["needs_retest"])

    def test_signed_plate_is_reserved(self):
        plates = plate_accounting(self.bundle)
        self.assertIn("P02", plates["signed_plates"])
        kinds = {(c["plate"], c["kind"]) for c in plates["conflicts"]}
        self.assertIn(("P02", "signed_reserved"), kinds)

    def test_split_requires_new_plate(self):
        plates = plate_accounting(self.bundle)
        self.assertEqual(plates["spare_plates"], [])
        self.assertTrue(plates["new_plate_required_for_split"])

    def test_submission_classification(self):
        context = submission_context(self.bundle)
        t1 = next(t for t in self.bundle.templates if t["template"] == "t1")
        result = evaluate_template(context, t1)
        classifications = {(r["product"], r["group"]): r["classification"] for r in result["results"]}
        self.assertEqual(classifications[("b", "普通读者")], "passes")
        self.assertIn(classifications[("a", "普通读者")], ("over_cap", "possibly_over_cap"))
        self.assertTrue(result["needs_split"])


class CorrectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = core.load(DATA)

    def test_correction_postdates_all_trials(self):
        impact = correction_impact(self.bundle)[0]
        self.assertEqual(impact["design"], "d5")
        self.assertGreater(impact["trials_before_known"], 0)
        self.assertEqual(impact["trials_after_known"], 0)

    def test_correction_rewires_order_contrast(self):
        impact = correction_impact(self.bundle)[0]
        by_block = {p["block"]: p for p in impact["pairs_changed"]}
        self.assertEqual(by_block["b3"]["layout_changed_before"], ["order", "emphasis"])
        self.assertEqual(by_block["b3"]["layout_changed_after"], ["order"])

    def test_corrected_evidence_is_not_usable_for_t2(self):
        review = {r["template"]: r for r in evidence_review(self.bundle)}
        self.assertFalse(review["t2"]["evidence_usable"])
        self.assertEqual(review["t2"]["touched_by_correction"], ["d5"])


if __name__ == "__main__":
    unittest.main()
