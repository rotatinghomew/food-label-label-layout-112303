"""Policy thresholds, per-product / per-reader-group compliance, and the
plate / shared-template decision.

The proxies
-----------
Two different quantities are needed:

* **Misunderstanding** is the share of comprehension tickets that fail to tell
  the two sugar statements apart (``meaning == 0``).  The policy caps it.
* **High-confidence error** is the share (of all tickets) that are wrong *and*
  marked confidence 4.  The policy caps it as well.

A design passes a product's policy if its *misunderstanding* is at or below the
cap, its *understanding* is at or above the product's floor, and high-confidence
error is at or below its cap, for the audience that applies.  Group floors take
precedence for named groups; product caps still apply.

Because a single template can exceed a cap only in a subgroup, a template is
also flagged when its pooled rate passes but a group's rate fails, or when one
product's advantage hides another product's breach.
"""
from __future__ import annotations

import math

from .core import Bundle, Spec
from .modeling import design_rates


def policy_table(bundle: Bundle) -> dict:
    """Index policy rows by (product, group) with ``*`` retained as wildcard."""
    table = {}
    for row in bundle.policy:
        table[(row["product"], row["group"])] = {
            "max_misunderstanding": float(row["max_misunderstanding"]),
            "min_understanding": float(row["min_understanding"]),
            "max_high_confidence_error": float(row["max_high_confidence_error"]),
        }
    return table


def applicable_policy(bundle: Bundle, product: str, group: str) -> dict:
    """Combine product caps with reader-group floors/caps, taking the stricter.

    Product rows carry the misunderstanding and high-confidence-error ceilings;
    reader rows carry the minimum-understanding floor (and stricter caps where
    they exist).  A template must satisfy both, so caps are the smaller of the
    two and floors the larger.
    """
    table = policy_table(bundle)
    product_row = table.get((product, "*"))
    group_row = table.get(("*", group))
    if product_row is None:
        raise KeyError(f"no product policy for {product!r}")
    max_mis = product_row["max_misunderstanding"]
    max_hce = product_row["max_high_confidence_error"]
    min_und = product_row["min_understanding"]
    if group_row is not None:
        max_mis = min(max_mis, group_row["max_misunderstanding"])
        max_hce = min(max_hce, group_row["max_high_confidence_error"])
        min_und = max(min_und, group_row["min_understanding"])
    return {
        "max_misunderstanding": max_mis,
        "min_understanding": min_und,
        "max_high_confidence_error": max_hce,
        "product_min_understanding": product_row["min_understanding"],
        "group_min_understanding": group_row["min_understanding"] if group_row is not None else None,
    }


def evaluate_rates(rates: list[dict], bundle: Bundle, *, attributes: dict[str, Spec] | None = None) -> list[dict]:
    """Attach pass/fail and the binding constraint to each design x group rate."""
    attributes = attributes or {}
    out = []
    for row in rates:
        design = row["design"]
        spec = attributes.get(design)
        product = spec.product if spec else _design_product(bundle, design)
        policy = applicable_policy(bundle, product, row["group"])
        misunderstanding = row["misunderstanding"]
        hce = row["hce"]
        checks = {
            "misunderstanding": misunderstanding <= policy["max_misunderstanding"],
            "understanding": row["understanding"] >= policy["min_understanding"],
            "high_confidence_error": hce <= policy["max_high_confidence_error"],
        }
        binding = [name for name, ok in checks.items() if not ok]
        out.append(
            {
                **row,
                "product": product,
                "policy": policy,
                "checks": checks,
                "pass": not binding,
                "failures": binding,
            }
        )
    return out


def _design_product(bundle: Bundle, design: str) -> str:
    return bundle.corrected_spec(design).product


def design_policy_matrix(bundle: Bundle, resolve: str = "corrected") -> dict:
    """Per design x group compliance, plus pooled and per-product roll-up."""
    obs_specs = {d: bundle.resolved_spec(d, _day(bundle), resolve) for d in bundle.designs}
    rates = evaluate_rates(design_rates(bundle, resolve), bundle, attributes=obs_specs)
    by_design: dict[str, dict] = {}
    for row in rates:
        by_design.setdefault(row["design"], {})[row["group"]] = row
    # per-product roll-up across designs that target that product
    products: dict[str, list[str]] = {}
    for design, spec in obs_specs.items():
        products.setdefault(spec.product, []).append(design)
    rollup = {}
    for product, designs in products.items():
        cell = {}
        for group in ("老读者", "普通读者"):
            relevant = [by_design[d][group] for d in designs if group in by_design[d]]
            if not relevant:
                continue
            # worst case per metric is what a product must satisfy
            cell[group] = {
                "worst_misunderstanding": max(r["misunderstanding"] for r in relevant),
                "worst_hce": max(r["hce"] for r in relevant),
                "min_understanding": min(r["understanding"] for r in relevant),
                "all_pass": all(r["pass"] for r in relevant),
                "failures": sorted({f for r in relevant for f in r["failures"]}),
                "designs": [r["design"] for r in relevant],
            }
        rollup[product] = cell
    return {"by_design": by_design, "by_product": rollup, "rates": rates}


def _day(bundle: Bundle) -> str:
    return max(t["day"] for t in bundle.trials)


# --------------------------------------------------------------------------- #
# templates
# --------------------------------------------------------------------------- #
def template_policy_report(bundle: Bundle, resolve: str = "corrected") -> list[dict]:
    """Evaluate every template against the policy of every product it lists."""
    from .templates import template_compatibility

    matrix = design_policy_matrix(bundle, resolve)
    compatibility = {r["template"]["template"]: r for r in template_compatibility(bundle)}
    rows = []
    for template in bundle.templates:
        products = bundle.template_products(template)
        specs = bundle.template_specs(template)
        designs = [d.strip() for d in template["designs"].split("/") if d.strip()]
        cells = bundle.template_cells(template)
        over_capacity = any(spec.cells > cells for spec in specs)
        product_cells = {
            product: max(
                (bundle.corrected_spec(d).cells for d in designs if bundle.corrected_spec(d).product == product),
                default=0,
            )
            for product in products
        }
        capacity_short = {p: c for p, c in product_cells.items() if c > cells}
        verdicts = {}
        for product in products:
            group_rows = {}
            for design in designs:
                spec = bundle.corrected_spec(design)
                if spec.product != product:
                    continue
                for group, row in matrix["by_design"].get(design, {}).items():
                    group_rows[group] = row
            if group_rows:
                failed = [g for g, r in group_rows.items() if not r["pass"]]
                verdicts[product] = {
                    "pass": all(r["pass"] for r in group_rows.values()),
                    "failed_groups": failed,
                    "rates": group_rows,
                }
        rows.append(
            {
                "template": template,
                "products": products,
                "designs": designs,
                "cells": cells,
                "over_capacity": over_capacity,
                "capacity_short": capacity_short,
                "compatible": compatibility[template["template"]]["compatible"],
                "mismatches": compatibility[template["template"]]["mismatches"],
                "verdicts": verdicts,
                "all_products_pass": all(v["pass"] for v in verdicts.values()) if verdicts else False,
                "any_product_pass": any(v["pass"] for v in verdicts.values()) if verdicts else False,
            }
        )
    return rows


def template_recommendation(bundle: Bundle, resolve: str = "corrected") -> list[dict]:
    """Decide keep / split / retest per candidate template, and note plate pressure."""
    report = template_policy_report(bundle, resolve)
    signed = bundle.signed()
    signed_plates = {t["plate"] for t in signed}
    candidate_plates: dict[str, list[str]] = {}
    for row in report:
        if row["template"]["status"] == "已签":
            continue
        candidate_plates.setdefault(row["template"]["plate"], []).append(row["template"]["template"])
    out = []
    for row in report:
        template = row["template"]
        plate = template["plate"]
        shared = candidate_plates.get(plate, [])
        plate_conflict = len(shared) > 1
        # A signed template is already on a plate: it is never "retested" from
        # scratch; the question is only whether to keep, re-review or withdraw.
        signed = template["status"] == "已签"
        incompatible = not row.get("compatible", True)
        if signed:
            if row["all_products_pass"]:
                verdict = "signed_keep"
            else:
                verdict = "signed_review"
        elif incompatible:
            # Cannot be tested as delivered on one plate; it must be rebuilt and
            # split before any new trial is meaningful.
            verdict = "rebuild_and_split"
        elif row["all_products_pass"]:
            verdict = "keep"
        elif any(v["pass"] for v in row["verdicts"].values()) and not row["all_products_pass"]:
            verdict = "split"
        elif row["verdicts"]:
            verdict = "retest"
        else:
            verdict = "unknown"
        if not signed and (row["over_capacity"] or row["capacity_short"]) and verdict == "keep":
            verdict = "split"
        out.append(
            {
                **row,
                "verdict": verdict,
                "plate": plate,
                "plate_shared_with_candidates": shared,
                "plate_conflict": plate_conflict,
                "plate_is_signed": plate in signed_plates,
                "needs_manual_split": verdict in ("split", "rebuild_and_split"),
                "needs_retest": verdict == "retest",
                "needs_review": verdict == "signed_review",
            }
        )
    return out
