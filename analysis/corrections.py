"""Impact of a recorded artwork correction on evidence and signed output."""
from __future__ import annotations

from .core import Bundle, Spec
from .identifiability import _pair_map


def correction_impact(bundle: Bundle) -> list[dict]:
    """For each correction: timing, affected trials/templates, and what changes."""
    out = []
    for correction in bundle.corrections:
        design = correction["design"]
        known = correction["known"]
        attribute = correction["attribute"]
        new_value = correction["new_value"]
        old_value = bundle.designs[design][attribute]

        affected_trials = [
            t for t in bundle.trials if known > t["day"] and design in (t["shown_left"], t["shown_right"])
        ]
        affected_after = [
            t for t in bundle.trials if known <= t["day"] and design in (t["shown_left"], t["shown_right"])
        ]
        # Templates that reference the design directly.
        templates = [
            t for t in bundle.templates if design in [d.strip() for d in t["designs"].split("/") if d.strip()]
        ]
        # Pairs (blocks) whose contrast changes because of the correction.
        pair_changes = _pairs_changed_by(bundle, design, attribute, old_value, new_value)
        out.append(
            {
                "event": correction["event"],
                "design": design,
                "attribute": attribute,
                "old_value": old_value,
                "new_value": new_value,
                "known": known,
                "trials_before_known": len(affected_trials),
                "trials_after_known": len(affected_after),
                "displayed_as_old": len(affected_trials) > 0,
                "templates_referencing": [t["template"] for t in templates],
                "signed_templates_referencing": [
                    t["template"] for t in templates if t["status"] == "已签"
                ],
                "candidate_templates_referencing": [
                    t["template"] for t in templates if t["status"] != "已签"
                ],
                "pairs_changed": pair_changes,
                "evidence_status": (
                    "contested: trials ran before the correction and used the old value"
                    if affected_trials
                    else "correction predates all trials; evidence uses the new value"
                ),
            }
        )
    return out


def _pairs_changed_by(bundle: Bundle, design: str, attribute: str, old: str, new: str) -> list[dict]:
    changed = []
    for block, row in sorted(bundle.blocks.items()):
        if design not in (row["left"], row["right"]):
            continue
        # Reconstruct the contrast under old vs new attribute value.
        old_specs = {}
        new_specs = {}
        for side in ("left", "right"):
            d = row[side]
            base = dict(bundle.designs[d])
            if d == design:
                base_old = dict(base)
                base_old[attribute] = old
                old_specs[side] = base_old
                base_new = dict(base)
                base_new[attribute] = new
                new_specs[side] = base_new
            else:
                old_specs[side] = base
                new_specs[side] = base
        old_changed = _layout_changes(old_specs["left"], old_specs["right"])
        new_changed = _layout_changes(new_specs["left"], new_specs["right"])
        if old_changed != new_changed:
            changed.append(
                {
                    "block": block,
                    "left": row["left"],
                    "right": row["right"],
                    "layout_changed_before": old_changed,
                    "layout_changed_after": new_changed,
                }
            )
    return changed


def _layout_changes(left: dict, right: dict) -> list[str]:
    keys = ("order", "emphasis", "copy", "required_cells", "product", "shape")
    return [k for k in keys if left[k] != right[k]]


def evidence_review(bundle: Bundle, resolve: str = "corrected") -> list[dict]:
    """Which templates still have usable evidence after applying corrections.

    A template's evidence is *usable* when the designs it references are not
    touched by a late correction, the delivered pairs isolate the attribute the
    template relies on, and the template is internally compatible.
    """
    from .identifiability import attribute_isolation, _pair_map
    from .templates import template_compatibility

    correction_designs = {c["design"] for c in bundle.corrections}
    isolation = attribute_isolation(bundle)["single_attribute_pairs"]
    compat = {row["template"]["template"]: row for row in template_compatibility(bundle)}
    pairs = _pair_map(bundle)

    # Which attributes any delivered pair isolates, after correction.
    isolated_attributes = {info["layout_changed"][0] for info in pairs.values() if info["single_attribute"]}

    out = []
    for template in bundle.templates:
        designs = [d.strip() for d in template["designs"].split("/") if d.strip()]
        touched = sorted(set(designs) & correction_designs)
        layout = compat[template["template"]]
        # Which attribute does this template vary across its designs?
        varied = _varied_attributes(bundle, designs)
        supported = sorted(set(varied) & isolated_attributes)
        out.append(
            {
                "template": template["template"],
                "status": template["status"],
                "designs": designs,
                "touched_by_correction": touched,
                "internally_compatible": layout["compatible"],
                "varied_attributes": sorted(varied),
                "isolated_by_delivered_pairs": supported,
                "evidence_usable": (
                    not touched and layout["compatible"] and bool(supported)
                ),
                "reason": _reason(touched, layout["compatible"], varied, supported),
            }
        )
    return out


def _varied_attributes(bundle: Bundle, designs: list[str]) -> set[str]:
    if len(designs) < 2:
        return set()
    specs = [bundle.corrected_spec(d) for d in designs]
    varied = set()
    for attr in ("order", "emphasis", "copy", "cells"):
        if len({getattr(s, attr) for s in specs}) > 1:
            varied.add(attr)
    return varied


def _reason(touched, compatible, varied, supported) -> str:
    parts = []
    if touched:
        parts.append(f"references corrected artwork {', '.join(touched)}")
    if not compatible:
        parts.append("designs cannot share one plate text")
    if not varied:
        parts.append("no attribute contrast among its designs")
    elif not supported:
        parts.append(f"delivered pairs never isolate {', '.join(sorted(varied))}")
    return "; ".join(parts) if parts else "evidence usable"
