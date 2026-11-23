"""Design identifiability: what the delivered pair design can and cannot isolate.

Uses exact rational row-reduction so that aliases are reported as exact
relationships rather than small singular values.
"""
from __future__ import annotations

from fractions import Fraction

import numpy as np

from .core import ATTRS, Bundle, Coder, Spec


def _rref(matrix: list[list[Fraction]]):
    mat = [row[:] for row in matrix]
    rows = len(mat)
    cols = len(mat[0]) if rows else 0
    pivots: list[int] = []
    r = 0
    for c in range(cols):
        pivot_row = next((i for i in range(r, rows) if mat[i][c] != 0), None)
        if pivot_row is None:
            continue
        mat[r], mat[pivot_row] = mat[pivot_row], mat[r]
        value = mat[r][c]
        mat[r] = [x / value for x in mat[r]]
        for i in range(rows):
            if i != r and mat[i][c] != 0:
                factor = mat[i][c]
                mat[i] = [a - factor * b for a, b in zip(mat[i], mat[r])]
        pivots.append(c)
        r += 1
        if r == rows:
            break
    return mat, pivots


def _nullspace(matrix: list[list[Fraction]], names: list[str]) -> list[dict[str, float]]:
    reduced, pivots = _rref(matrix)
    free = [c for c in range(len(names)) if c not in pivots]
    basis = []
    for f in free:
        vector = [Fraction(0)] * len(names)
        vector[f] = Fraction(1)
        for i, c in enumerate(pivots):
            vector[c] = -reduced[i][f]
        basis.append(
            {names[j]: float(coef) for j, coef in enumerate(vector) if coef != 0}
        )
    return basis


def _pack_row(spec: Spec, packs: list[str]) -> list[Fraction]:
    """Indicator row for product x shape, layout attributes and cell count."""
    return [Fraction(1)] + [
        Fraction(spec.pack == p) for p in packs[1:]
    ] + [
        Fraction(spec.order == "成分先"),
        Fraction(spec.emphasis == "突出"),
        Fraction(spec.copy == "无附加说明"),
        Fraction(spec.cells == 3),
    ]


PACK_NAMES = ["intercept", "pack_b-方", "pack_b-长", "pack_c-长", "order=成分先", "emph=突出", "copy=无说明", "cells=3"]


def design_identifiability(bundle: Bundle) -> dict:
    """Rank / aliases of the delivered design set, as displayed and corrected."""
    packs = sorted({bundle.corrected_spec(d).pack for d in bundle.designs})
    report = {}
    for label, resolve in (("as_recorded", "as_recorded"), ("corrected", "corrected")):
        specs = {
            d: (bundle.displayed_spec(d, _earliest_day(bundle)) if resolve == "as_recorded" else bundle.corrected_spec(d))
            for d in bundle.designs
        }
        design_matrix = [_pack_row(specs[d], packs) for d in sorted(specs)]
        reduced, pivots = _rref(design_matrix)
        pair_matrix = []
        for block, row in sorted(bundle.blocks.items()):
            left = bundle.resolved_spec(row["left"], _earliest_day(bundle), resolve)
            right = bundle.resolved_spec(row["right"], _earliest_day(bundle), resolve)
            pair_matrix.append([a - b for a, b in zip(_pack_row(left, packs), _pack_row(right, packs))])
        pair_reduced, pair_pivots = _rref(pair_matrix)
        report[label] = {
            "designs": len(specs),
            "design_rank": len(pivots),
            "design_columns": len(PACK_NAMES),
            "design_aliases": _nullspace(design_matrix, PACK_NAMES),
            "pair_rank": len(pair_pivots),
            "pair_columns": len(PACK_NAMES),
            "pair_aliases": _nullspace(pair_matrix, PACK_NAMES),
        }
    report["packs"] = packs
    report["pair_map"] = _pair_map(bundle)
    return report


def _earliest_day(bundle: Bundle) -> str:
    return min(row["day"] for row in bundle.trials)


ATTR_KEYS = ("order", "emphasis", "copy", "cells")


def _pair_map(bundle: Bundle) -> dict[str, dict]:
    out = {}
    for block, row in sorted(bundle.blocks.items()):
        left = bundle.corrected_spec(row["left"])
        right = bundle.corrected_spec(row["right"])
        differences = {
            "order": (left.order, right.order),
            "emphasis": (left.emphasis, right.emphasis),
            "copy": (left.copy, right.copy),
            "cells": (left.cells, right.cells),
            "pack": (left.pack, right.pack),
        }
        changed = [k for k, (a, b) in differences.items() if a != b]
        layout_changed = [k for k in changed if k in ATTR_KEYS]
        out[block] = {
            "left": row["left"],
            "right": row["right"],
            "changed": changed,
            "layout_changed": layout_changed,
            "single_attribute": len(layout_changed) == 1 and len(changed) == 1,
        }
    return out


def attribute_isolation(bundle: Bundle) -> dict:
    """How many pairs change each attribute *alone* (corrected artwork)."""
    counts = {a: 0 for a in ATTR_KEYS}
    for block, info in _pair_map(bundle).items():
        if info["single_attribute"]:
            counts[info["layout_changed"][0]] += 1
    return {"single_attribute_pairs": counts, "pairs": _pair_map(bundle)}


def copy_cell_alias(bundle: Bundle) -> dict:
    """Within the observed designs, does copy ever vary independently of cells?"""
    table: dict[tuple[str, int], list[str]] = {}
    for design in sorted(bundle.designs):
        spec = bundle.corrected_spec(design)
        table.setdefault(spec.copy_bundle, []).append(design)
    reverse: dict[str, set[int]] = {}
    for (copy, cells) in table:
        reverse.setdefault(copy, set()).add(cells)
    return {
        "copy_cell_pairs": {f"{k[0]}|cells={k[1]}": v for k, v in sorted(table.items())},
        "aliased": all(len(v) == 1 for v in reverse.values()) and len(reverse) > 1,
    }


def comparison_components(bundle: Bundle) -> list[list[str]]:
    """Connected components of the pair graph: contrasts do not cross these."""
    parent = {d: d for d in bundle.designs}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        parent[find(a)] = find(b)

    for row in bundle.blocks.values():
        union(row["left"], row["right"])
    components: dict[str, list[str]] = {}
    for design in bundle.designs:
        components.setdefault(find(design), []).append(design)
    return sorted((sorted(v) for v in components.values()), key=lambda v: v[0])


def position_confound(bundle: Bundle) -> dict:
    """Is side position crossed with artwork, or fixed within each pair?"""
    per_block = {}
    for block, row in bundle.blocks.items():
        seen = {
            (t["shown_left"], t["shown_right"])
            for t in bundle.trials
            if t["block"] == block and t["shown_left"] and t["shown_right"]
        }
        per_block[block] = {
            "scheduled": (row["left"], row["right"]),
            "observed_orders": sorted(seen),
        }
    fixed = all(len(v["observed_orders"]) == 1 for v in per_block.values())
    # A design shown on the left in one pair and the right in another would let
    # the position main effect separate from artwork; check the observed sides.
    sides: dict[str, set[str]] = {}
    for t in bundle.trials:
        for side in ("left", "right"):
            design = t["shown_" + side]
            if design:
                sides.setdefault(design, set()).add(side)
    crossed_designs = sorted(d for d, s in sides.items() if len(s) == 2)
    return {
        "per_block": per_block,
        "position_fixed_within_block": fixed,
        "crossed_designs": crossed_designs,
        "position_identified_from_crossing": bool(crossed_designs),
    }


def misinformation_flags(bundle: Bundle) -> list[dict]:
    """Designs whose shorthand can be read as "no sugar" despite a claim.

    Flagged for review: the sugar statement is present but the design also
    carries a no-added-sugar / no-description cue, so a 'misunderstanding' is
    a real confusion risk rather than a trivially different artwork.
    """
    flags = []
    for design in sorted(bundle.designs):
        spec = bundle.corrected_spec(design)
        if spec.copy == "无附加说明":
            flags.append(
                {
                    "design": design,
                    "spec": spec,
                    "reason": "no supplemental text: reader must infer the sugar claim from the front",
                }
            )
    return flags


# --------------------------------------------------------------------------- #
# copy vs shape vs cells: "can these be told apart?"
# --------------------------------------------------------------------------- #
LEVELS = {
    "order": ("成分先", "声明先"),
    "emphasis": ("突出", "普通"),
    "copy": ("未加蔗糖说明", "无附加说明"),
    "cells": (5, 3),
    "shape": ("圆", "方", "长"),
}

PLATE_ATTRS = ("order", "emphasis", "copy", "cells")
BOTTLE_ATTRS = ("shape", "product")


def _value(spec: Spec, attribute: str):
    return getattr(spec, attribute)


def pairwise_separability(bundle: Bundle) -> dict:
    """For each attribute, which other attributes were held fixed in a pair
    that changed it.  An attribute is isolated only if some pair changes it and
    nothing else on the plate."""
    pairs = [
        (block, bundle.corrected_spec(row["left"]), bundle.corrected_spec(row["right"]))
        for block, row in sorted(bundle.blocks.items())
    ]
    out: dict[str, dict] = {}
    for a in PLATE_ATTRS + BOTTLE_ATTRS:
        out[a] = {
            "levels": sorted(
                {_value(bundle.corrected_spec(d), a) for d in bundle.designs}, key=str
            ),
            "held_fixed_in_changing_pairs": {},
        }
        for b in PLATE_ATTRS + BOTTLE_ATTRS:
            if a == b:
                continue
            opportunities = set()
            for _block, left, right in pairs:
                if _value(left, b) == _value(right, b) and _value(left, a) != _value(right, a):
                    opportunities.add(
                        (
                            _value(left, b),
                            tuple(sorted({_value(left, a), _value(right, a)}, key=str)),
                        )
                    )
            out[a]["held_fixed_in_changing_pairs"][b] = sorted(opportunities, key=str)
    return out


def copy_shape_cells_table(bundle: Bundle) -> list[dict]:
    """Cross-tab of copy text, cell count and bottle shape across artworks."""
    return [
        {
            "design": design,
            "copy": bundle.corrected_spec(design).copy,
            "cells": bundle.corrected_spec(design).cells,
            "shape": bundle.corrected_spec(design).shape,
            "product": bundle.corrected_spec(design).product,
        }
        for design in sorted(bundle.designs)
    ]


def copy_shape_verdict(bundle: Bundle) -> dict:
    """Answer directly: are the removed description, the bottle shape and the
    cell count separable in the delivered data?"""
    table = copy_shape_cells_table(bundle)
    copies = sorted({r["copy"] for r in table})
    shapes = sorted({r["shape"] for r in table})
    cells_by_copy = {c: sorted({r["cells"] for r in table if r["copy"] == c}) for c in copies}
    shapes_by_copy = {c: sorted({r["shape"] for r in table if r["copy"] == c}) for c in copies}
    copies_by_shape = {
        s: sorted({r["copy"] for r in table if r["shape"] == s}) for s in shapes
    }
    no_copy_shapes = sorted({r["shape"] for r in table if r["copy"] == "无附加说明"})
    alias = copy_cell_alias(bundle)["aliased"]
    shape_has_copy_variation = any(len(v) > 1 for v in copies_by_shape.values())
    copy_has_shape_variation = any(len(v) > 1 for v in shapes_by_copy.values())
    return {
        "cells_by_copy": cells_by_copy,
        "shapes_by_copy": shapes_by_copy,
        "copies_by_shape": copies_by_shape,
        "no_copy_shapes": no_copy_shapes,
        "copy_aliased_with_cells": alias,
        "copy_separable_from_shape": shape_has_copy_variation and copy_has_shape_variation,
        "copy_separable_from_cells": not alias,
        "explanation": _copy_shape_explanation(
            cells_by_copy, shapes_by_copy, copies_by_shape, no_copy_shapes, alias
        ),
    }


def _copy_shape_explanation(cells_by_copy, shapes_by_copy, copies_by_shape, no_copy_shapes, alias) -> str:
    parts = []
    if alias:
        parts.append("删说明与少占格完全别名（无说明=3 格，有说明=5 格），不能分别估计")
    if copies_by_shape and all(len(v) == 1 for v in copies_by_shape.values()):
        parts.append("每种瓶型只有一个文案水平，文案与瓶型不可分")
    else:
        parts.append("文案在部分瓶型内变化，可与瓶型分开")
    parts.append(f"无说明版只出现在瓶型 {'/'.join(no_copy_shapes)}")
    return "；".join(parts) + "。"
