"""Evaluate a *new* artwork / template submission with the same yardstick.

An editor submits, per product, a set of artwork specs (or a template with a
design list).  This module reports, per product x reader group:

* whether the pack has evidence in the delivered design (estimable) or not;
* whether the plate has room (capacity);
* the estimated misunderstanding / understanding / high-confidence error and
  whether they clear policy, with the same clustered uncertainty.

The classification an editor sees is exactly one of:

``plate_short``      the plate cannot hold the required cells for a product;
``not_estimable``    no delivered evidence covers this product/pack/attribute;
``possibly_over_cap`` estimated, but the interval or point estimate breaches a
                     misunderstanding / HCE cap;
``passes``           estimated and clears every applicable threshold.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.special import expit

from .core import Bundle, Coder, Spec
from .modeling import fit_suite
from .policy import applicable_policy


def submission_context(bundle: Bundle) -> dict:
    """Precompute fits and the set of packs / attribute levels with evidence."""
    suite = fit_suite(bundle)
    coder = suite["coder"]
    evidence_packs = {coder.vec(o.spec).tolist() and o.spec.pack for o in suite["obs"]}
    evidence_packs = {o.spec.pack for o in suite["obs"]}
    return {"suite": suite, "coder": coder, "evidence_packs": evidence_packs, "bundle": bundle}


def evaluate_spec(context: dict, spec: Spec, *, plate_cells: int | None = None, group: str = "普通读者") -> dict:
    suite = context["suite"]
    coder = context["coder"]
    bundle = context["bundle"]
    from .modeling import predict_logit

    pm = predict_logit(suite["meaning"], coder, spec, group)
    ph = predict_logit(suite["hce"], coder, spec, group)
    policy = applicable_policy(bundle, spec.product, group)

    estimable = spec.pack in context["evidence_packs"] and coder.has_pack(spec)
    capacity_ok = plate_cells is None or spec.cells <= plate_cells
    # Does a delivered pair isolate this attribute?  Without that, the
    # attribute part of the prediction is extrapolated from a bundle of
    # attributes, not from an isolated contrast.
    from .identifiability import attribute_isolation

    isolation = attribute_isolation(bundle)["single_attribute_pairs"]
    isolated_attrs = {a for a, n in isolation.items() if n > 0}

    misunderstanding = 1.0 - pm["prob"]
    misunderstanding_lo = 1.0 - pm["hi"]
    misunderstanding_hi = 1.0 - pm["lo"]
    # A point-estimate breach is a hard fail; an interval that straddles the cap
    # is an "insufficient evidence to clear" result.  Editors see both.
    point_breach = (
        misunderstanding > policy["max_misunderstanding"]
        or ph["prob"] > policy["max_high_confidence_error"]
        or pm["prob"] < policy["min_understanding"]
    )
    interval_breach = (
        misunderstanding_hi > policy["max_misunderstanding"]
        or ph["hi"] > policy["max_high_confidence_error"]
        or pm["lo"] < policy["min_understanding"]
    )
    if not capacity_ok:
        classification = "plate_short"
    elif not estimable:
        classification = "not_estimable"
    elif point_breach:
        classification = "over_cap"
    elif interval_breach:
        classification = "possibly_over_cap"
    else:
        classification = "passes"

    return {
        "spec": spec,
        "group": group,
        "product": spec.product,
        "pack": spec.pack,
        "plate_cells": plate_cells,
        "capacity_ok": capacity_ok,
        "estimable": estimable,
        "isolated_attributes": sorted(isolated_attrs),
        "understanding": pm,
        "hce": ph,
        "misunderstanding": misunderstanding,
        "misunderstanding_interval": (misunderstanding_lo, misunderstanding_hi),
        "point_breach": point_breach,
        "interval_breach": interval_breach,
        "policy": policy,
        "classification": classification,
        "explanation": _explain(classification, spec, plate_cells, policy, pm, ph),
    }


def _explain(classification, spec, plate_cells, policy, pm, ph) -> str:
    if classification == "plate_short":
        return f"{spec.pack} needs {spec.cells} cells but the plate holds {plate_cells}"
    if classification == "not_estimable":
        return f"no delivered evidence covers pack {spec.pack}; cannot estimate without new trials"
    if classification == "over_cap":
        if 1.0 - pm["prob"] > policy["max_misunderstanding"]:
            return (
                f"estimated misunderstanding {1.0 - pm['prob']:.3f} exceeds cap "
                f"{policy['max_misunderstanding']:.3f}"
            )
        if ph["prob"] > policy["max_high_confidence_error"]:
            return (
                f"estimated high-confidence error {ph['prob']:.3f} exceeds cap "
                f"{policy['max_high_confidence_error']:.3f}"
            )
        return f"estimated understanding {pm['prob']:.3f} below floor {policy['min_understanding']:.3f}"
    if classification == "possibly_over_cap":
        if 1.0 - pm["lo"] > policy["max_misunderstanding"]:
            return (
                f"misunderstanding upper bound {1.0 - pm['lo']:.3f} exceeds cap "
                f"{policy['max_misunderstanding']:.3f}; point estimate does not"
            )
        if ph["hi"] > policy["max_high_confidence_error"]:
            return (
                f"high-confidence error upper bound {ph['hi']:.3f} exceeds cap "
                f"{policy['max_high_confidence_error']:.3f}; point estimate does not"
            )
        return (
            f"understanding lower bound {pm['lo']:.3f} below floor "
            f"{policy['min_understanding']:.3f}; point estimate does not"
        )
    return "estimated and clears every applicable threshold"


def evaluate_template(context: dict, template: dict) -> dict:
    """Evaluate a template's design list per product and per group."""
    bundle = context["bundle"]
    designs = [d.strip() for d in template["designs"].split("/") if d.strip()]
    products = [p.strip() for p in template["products"].split("/") if p.strip()]
    cells = int(template["cells"])
    specs = [bundle.corrected_spec(d) for d in designs]
    results = []
    for product in products:
        for group in ("老读者", "普通读者"):
            product_specs = [s for s in specs if s.product == product]
            if not product_specs:
                results.append(
                    {
                        "product": product,
                        "group": group,
                        "classification": "not_estimable",
                        "explanation": f"template lists no artwork for product {product}",
                    }
                )
                continue
            worst = None
            for spec in product_specs:
                row = evaluate_spec(context, spec, plate_cells=cells, group=group)
                if worst is None or _severity(row) > _severity(worst):
                    worst = row
            results.append(
                {
                    "product": product,
                    "group": group,
                    **{k: worst[k] for k in (
                        "pack", "plate_cells", "capacity_ok", "estimable",
                        "understanding", "hce", "misunderstanding",
                        "misunderstanding_interval", "policy", "classification", "explanation",
                    )},
                }
            )
    return {
        "template": template["template"],
        "products": products,
        "designs": designs,
        "cells": cells,
        "results": results,
        "all_pass": all(r["classification"] == "passes" for r in results),
        "needs_split": any(r["classification"] != "passes" for r in results)
        and any(r["classification"] == "passes" for r in results),
        "needs_retest": all(r["classification"] in ("not_estimable",) for r in results),
    }


def _severity(row: dict) -> tuple:
    order = {"plate_short": 4, "not_estimable": 3, "over_cap": 2, "possibly_over_cap": 1, "passes": 0}
    return (order.get(row["classification"], 9), row.get("misunderstanding", 0.0))


def attribute_change_impact(context: dict, template: dict, attribute: str) -> dict:
    """Which products are re-tested / re-plated if one shared attribute changes."""
    bundle = context["bundle"]
    designs = [d.strip() for d in template["designs"].split("/") if d.strip()]
    products = [p.strip() for p in template["products"].split("/") if p.strip()]
    affected = {}
    for product in products:
        relevant = [d for d in designs if bundle.corrected_spec(d).product == product]
        affected[product] = relevant
    from .templates import plate_accounting

    accounting = plate_accounting(bundle)
    return {
        "template": template["template"],
        "attribute": attribute,
        "products_affected": list(affected),
        "designs_affected": {p: v for p, v in affected.items()},
        "spare_plates": accounting["spare_plates"],
        "reusable_for_split": accounting["available_for_new_signature"],
        "plate_conflicts": accounting["conflicts"],
        "note": (
            "changing this shared attribute re-evaluates every listed product; "
            "a split consumes an additional plate and no spare plate is available"
            if not accounting["available_for_new_signature"]
            else "changing this attribute re-evaluates every listed product"
        ),
    }
