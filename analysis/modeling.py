"""Estimate the effects of layout attributes on choice, understanding and
high-confidence error, and test which effects survive held-out checks.
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
from scipy.special import expit
from scipy.stats import chi2

from .core import (
    Bundle,
    Coder,
    Fit,
    Choice,
    Obs,
    choices,
    coder_for,
    fit_choice,
    fit_logit,
    fit_pair_fe,
    lr_test,
    observations,
    predict_choice_share,
    predict_logit,
)


def fit_suite(bundle: Bundle, resolve: str = "corrected") -> dict:
    coder = coder_for(bundle, resolve)
    obs = observations(bundle, resolve)
    ch = choices(bundle, resolve)
    rows = [
        {"person": o.person, "group": o.group, "spec": o.spec,
         "meaning": o.meaning, "hce": o.hce, "design": o.design}
        for o in obs
    ]
    choice_fit = fit_choice(coder, ch)
    pair_fe = fit_pair_fe(ch)
    meaning_fit = fit_logit(coder, rows, "meaning")
    hce_fit = fit_logit(coder, rows, "hce")
    meaning_group = fit_logit(
        coder, rows, "meaning", group_main=True, group_inter=("order=成分先", "emph=突出", "copy=无说明")
    )
    hce_group = fit_logit(
        coder, rows, "hce", group_main=True, group_inter=("order=成分先", "emph=突出", "copy=无说明")
    )
    product_terms = tuple(
        f"pack:{p}" for p in coder.packs[1:]
    )
    return {
        "resolve": resolve,
        "coder": coder,
        "obs": obs,
        "choices": ch,
        "choice": choice_fit,
        "pair_fe": pair_fe,
        "choice_vs_pair": lr_test(choice_fit, pair_fe),
        "meaning": meaning_fit,
        "hce": hce_fit,
        "meaning_group": meaning_group,
        "hce_group": hce_group,
        "meaning_group_lr": lr_test(meaning_fit, meaning_group),
        "hce_group_lr": lr_test(hce_fit, hce_group),
        "packs": coder.packs,
    }


def choice_sensitivity(bundle: Bundle) -> dict:
    """Choice model under both attribute resolutions and with a side term."""
    out = {}
    for resolve in ("corrected", "as_recorded"):
        coder = coder_for(bundle, resolve)
        ch = choices(bundle, resolve)
        base = fit_choice(coder, ch)
        pos = fit_choice(coder, ch, include_position=True)
        out[resolve] = {"base": base, "with_position": pos}
    return out


def effect_table(fit_: Fit, coder: Coder, *, terms: tuple[str, ...] | None = None) -> list[dict]:
    """Odds ratio and cluster-robust 95% CI for the attribute terms."""
    terms = terms or tuple(coder.names)
    rows = []
    for name in terms:
        if name not in fit_.names:
            continue
        i = fit_.names.index(name)
        beta, se = float(fit_.beta[i]), float(fit_.se[i])
        rows.append(
            {
                "term": name,
                "coef": beta,
                "se": se,
                "odds_ratio": math.exp(beta) if abs(beta) < 50 else math.inf,
                "lo": math.exp(beta - 1.96 * se),
                "hi": math.exp(beta + 1.96 * se),
                "p": float(2 * (1 - _norm_cdf(abs(beta / se)))) if se > 0 else 1.0,
            }
        )
    return rows


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def design_rates(bundle: Bundle, resolve: str = "corrected") -> list[dict]:
    """Descriptive rates per artwork with cluster-bootstrap CIs by person.

    Bootstrap resamples people (not tickets) so repeated judgements are not
    treated as independent.
    """
    obs = observations(bundle, resolve)
    persons = sorted({o.person for o in obs})
    index = {p: i for i, p in enumerate(persons)}
    designs = sorted({o.design for o in obs})
    d_index = {d: i for i, d in enumerate(designs)}
    groups = ["老读者", "普通读者"]

    counts = {(g, "n"): np.zeros((len(persons), len(designs))) for g in groups}
    counts.update({(g, "u"): np.zeros((len(persons), len(designs))) for g in groups})
    counts.update({(g, "h"): np.zeros((len(persons), len(designs))) for g in groups})
    for o in obs:
        i, j = index[o.person], d_index[o.design]
        counts[(o.group, "n")][i, j] += 1
        counts[(o.group, "u")][i, j] += o.meaning
        counts[(o.group, "h")][i, j] += o.hce

    rng = np.random.default_rng(20261123)
    reps = 4000
    results = {}
    for group in groups + ["ALL"]:
        if group == "ALL":
            n = counts[("老读者", "n")] + counts[("普通读者", "n")]
            u = counts[("老读者", "u")] + counts[("普通读者", "u")]
            h = counts[("老读者", "h")] + counts[("普通读者", "h")]
        else:
            n, u, h = counts[(group, "n")], counts[(group, "u")], counts[(group, "h")]
        boot_u, boot_h = [], []
        for _ in range(reps):
            sample = rng.integers(0, len(persons), len(persons))
            nn = n[sample].sum(0)
            uu = u[sample].sum(0)
            hh = h[sample].sum(0)
            with np.errstate(invalid="ignore", divide="ignore"):
                boot_u.append(np.where(nn > 0, uu / nn, np.nan))
                boot_h.append(np.where(nn > 0, hh / nn, np.nan))
        boot_u = np.asarray(boot_u)
        boot_h = np.asarray(boot_h)
        for j, design in enumerate(designs):
            total = n[:, j].sum()
            results[(group, design)] = {
                "group": group,
                "design": design,
                "n": int(total),
                "understanding": float(u[:, j].sum() / total) if total else float("nan"),
                "misunderstanding": float(1 - u[:, j].sum() / total) if total else float("nan"),
                "hce": float(h[:, j].sum() / total) if total else float("nan"),
                "understanding_ci": _pct(boot_u[:, j]),
                "hce_ci": _pct(boot_h[:, j]),
            }
    return [results[(g, d)] for g in groups + ["ALL"] for d in designs]


def _pct(values: np.ndarray) -> tuple[float, float]:
    values = values[~np.isnan(values)]
    if values.size == 0:
        return (float("nan"), float("nan"))
    lo, hi = np.percentile(values, [2.5, 97.5])
    return (float(lo), float(hi))


def fitted_predictions(suite: dict) -> list[dict]:
    """Observed vs fitted understanding / HCE for each artwork."""
    coder = suite["coder"]
    rows = []
    design_values = sorted({o.design for o in suite["obs"]})
    for design in design_values:
        spec = next(o.spec for o in suite["obs"] if o.design == design)
        pm = predict_logit(suite["meaning"], coder, spec)
        ph = predict_logit(suite["hce"], coder, spec)
        sub = [o for o in suite["obs"] if o.design == design]
        rows.append(
            {
                "design": design,
                "spec": spec,
                "observed_understanding": float(np.mean([o.meaning for o in sub])),
                "fitted_understanding": pm["prob"],
                "observed_hce": float(np.mean([o.hce for o in sub])),
                "fitted_hce": ph["prob"],
            }
        )
    return rows


def choice_shares(bundle: Bundle, resolve: str = "corrected") -> list[dict]:
    """Observed and model-predicted shares for each delivered pair."""
    coder = coder_for(bundle, resolve)
    ch = choices(bundle, resolve)
    fit_ = fit_choice(coder, ch)
    rows = []
    for block, block_row in sorted(bundle.blocks.items()):
        sub = [c for c in ch if c.block == block]
        if not sub:
            continue
        left = bundle.resolved_spec(block_row["left"], bundle.trials[0]["day"], resolve)
        right = bundle.resolved_spec(block_row["right"], bundle.trials[0]["day"], resolve)
        pred = predict_choice_share(fit_, coder, left, right)
        n = len(sub)
        obs = [sum(1 for c in sub if c.choice == k) / n for k in range(3)]
        rows.append(
            {
                "block": block,
                "left": block_row["left"],
                "right": block_row["right"],
                "n": n,
                "observed": {"left": obs[0], "right": obs[1], "none": obs[2]},
                "predicted": pred,
            }
        )
    return rows
