"""Shared-template compatibility, plate accounting and correction impact.

A shared plate can only carry *identical fixed text* at the same position.  Two
designs can therefore share one template only if they agree on every layout
property the plate encodes: copy text, statement order, emphasis and the cell
requirement (which must fit the plate's capacity).  Product and bottle shape
may differ, because the template lists them separately.

Plates are a hard resource.  A signed plate is reserved for the product it
serves until that product switches; a candidate may not silently reuse it for a
different, incompatible text set to avoid a split.
"""
from __future__ import annotations

from .core import ATTRS, Bundle, Spec


def layout_signature(spec: Spec) -> tuple:
    return (spec.copy, spec.order, spec.emphasis, spec.cells)


def template_compatibility(bundle: Bundle) -> list[dict]:
    rows = []
    for template in bundle.templates:
        designs = [d.strip() for d in template["designs"].split("/") if d.strip()]
        specs = [bundle.corrected_spec(d) for d in designs]
        signatures = {layout_signature(s) for s in specs}
        products = bundle.template_products(template)
        shapes = bundle.template_shapes(template)
        cells = bundle.template_cells(template)
        copy_text = template["copy"]

        mismatches = []
        # "不同说明" explicitly declares that the designs carry different fixed
        # texts; one plate cannot hold two texts.  "保留的既有文字" is a
        # placeholder for signed artwork and inherits each design's copy.
        if copy_text == "不同说明":
            mismatches.append("template declares differing copy text; one plate cannot hold two texts")
        for spec in specs:
            if copy_text not in ("不同说明", "保留的既有文字") and spec.copy != copy_text:
                mismatches.append(f"{spec.pack} copy {spec.copy!r} != template {copy_text!r}")
            if spec.pack.split("-", 1)[0] not in products:
                mismatches.append(f"{spec.pack} product not listed")
            if spec.shape not in shapes:
                mismatches.append(f"{spec.pack} shape not listed")
            if spec.cells > cells:
                mismatches.append(f"{spec.pack} needs {spec.cells} cells > plate {cells}")
        if len(signatures) > 1:
            mismatches.append("designs disagree on layout signature (copy/order/emphasis/cells)")
        rows.append(
            {
                "template": template,
                "designs": designs,
                "specs": specs,
                "products": products,
                "shapes": shapes,
                "cells": cells,
                "copy": copy_text,
                "signatures": sorted(signatures),
                "compatible": not mismatches,
                "mismatches": mismatches,
                "layout_uniform": len(signatures) == 1,
            }
        )
    return rows


def plate_accounting(bundle: Bundle) -> dict:
    """Plates referenced, which are signed/reserved, and which are contested."""
    signed = bundle.signed()
    candidates = bundle.candidates()
    plates: dict[str, dict] = {}
    for template in bundle.templates:
        plate = template["plate"]
        entry = plates.setdefault(plate, {"signed": [], "candidates": []})
        if template["status"] == "已签":
            entry["signed"].append(template["template"])
        else:
            entry["candidates"].append(template["template"])

    compatibility = {row["template"]["template"]: row for row in template_compatibility(bundle)}
    signed_plates = {t["plate"] for t in signed}
    candidate_plates = {t["plate"] for t in candidates}
    all_plates = set(plates)

    # Layout signatures already committed to each plate.  A plate can host any
    # number of templates only if they share exactly one signature; a split
    # that introduces a *different* text/layout signature always needs a plate
    # that is not carrying an incompatible set already.
    plate_signatures: dict[str, set] = {}
    for template in bundle.templates:
        info = compatibility[template["template"]]
        plate_signatures.setdefault(template["plate"], set()).update(info["signatures"])

    signed_signature = {
        t["plate"]: compatibility[t["template"]]["signatures"]
        for t in signed
        if compatibility[t["template"]]["signatures"]
    }

    # Spare: not signed, not claimed by any candidate.
    spare = sorted(all_plates - signed_plates - candidate_plates)

    # A plate can absorb a *new, different* signature only if it is spare (or
    # every current holder is unsigned and the new signature is added as a
    # separate template; a plate physically holds one text per position, so an
    # incompatible addition always costs a plate).
    conflicts = []
    for plate, entry in plates.items():
        # Signed plate + any candidate on the same plate is a conflict: the
        # signed plate is reserved for the product it serves.
        if entry["signed"] and entry["candidates"]:
            conflicts.append(
                {
                    "plate": plate,
                    "kind": "signed_reserved",
                    "signed": entry["signed"],
                    "candidates": entry["candidates"],
                    "message": "signed plate is reserved for its product; candidates must not reuse it",
                }
            )
        # Multiple candidates on one plate are only allowed if their text sets
        # are identical; otherwise they cannot both use the plate.
        if len(entry["candidates"]) > 1:
            texts = {
                tuple(sorted(compatibility[c]["signatures"]))
                for c in entry["candidates"]
            }
            if len(texts) > 1:
                conflicts.append(
                    {
                        "plate": plate,
                        "kind": "incompatible_candidates",
                        "candidates": entry["candidates"],
                        "message": "candidates carry incompatible text sets and cannot share this plate",
                    }
                )
    # A split needs one extra incompatible text set.  No spare plate and no
    # candidate plate that is free of a signed reservation means a new plate.
    available_for_new_signature = [p for p in spare if p not in signed_plates]
    return {
        "plates": plates,
        "signed_plates": sorted(signed_plates),
        "candidate_plates": sorted(candidate_plates),
        "spare_plates": spare,
        "available_for_new_signature": available_for_new_signature,
        "conflicts": conflicts,
        "new_plate_required_for_split": not available_for_new_signature,
    }


def shared_attribute_impact(bundle: Bundle, template_id: str) -> dict:
    """If one shared attribute on this template changes, which products move?"""
    template = next(t for t in bundle.templates if t["template"] == template_id)
    designs = [d.strip() for d in template["designs"].split("/") if d.strip()]
    products = bundle.template_products(template)
    per_product = {}
    for product in products:
        relevant = [d for d in designs if bundle.corrected_spec(d).product == product]
        per_product[product] = {
            "designs": relevant,
            "signatures": [layout_signature(bundle.corrected_spec(d)) for d in relevant],
        }
    shared = {
        "template": template_id,
        "products": list(products),
        "per_product": per_product,
        "a_change_touches": list(products),
        "note": "one shared attribute change re-tests or re-plates every listed product at once",
    }
    accounting = plate_accounting(bundle)
    shared["plate"] = template["plate"]
    shared["spare_plates"] = accounting["spare_plates"]
    shared["available_for_new_signature"] = accounting["available_for_new_signature"]
    shared["new_plate_required_for_split"] = accounting["new_plate_required_for_split"]
    shared["plate_conflicts"] = accounting["conflicts"]
    return shared
