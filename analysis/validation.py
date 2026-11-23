"""Held-out checks: what transfers to a new artwork, and what is only
descriptive of the combinations already shown.

Three checks:

1. **Pair hold-out** (leave-one-pair-out): refit the choice model without a
   pair, predict that pair.  This is the only honest test of "would this
   transfer to a new pair?" because it never sees the target combination.
2. **Artwork hold-out** (leave-one-design-out): refit the comprehension model
   without a design, predict it.  Tests attribute extrapolation.
3. **Simultaneous / crossed hold-out**: leave out an entire product-pack, to
   show where the model is extrapolating rather than interpolating.

Hold-out fits use a modest ridge (``HOLDOUT_RIDGE``).  A high-confidence-error
cell with zero events under complete separation otherwise drives coefficients
to +/-infinity and produces meaningless predictions of 0 or 1; the ridge keeps
the exercise about accuracy rather than separation artefacts.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.special import expit, logsumexp

from .core import Bundle, Coder, Fit, Choice, Obs
from .modeling import fit_suite

HOLDOUT_RIDGE = 2.0


def leave_one_pair_out(bundle: Bundle, resolve: str = "corrected") -> list[dict]:
    coder = _coder(bundle, resolve)
    rows = _choices(bundle, resolve)
    blocks = sorted({r.block for r in rows})
    uniform = math.log(3)
    out = []
    for block in blocks:
        train = [r for r in rows if r.block != block]
        test = [r for r in rows if r.block == block]
        fit_ = _fit_choice(coder, train)
        ll = 0.0
        pred_left_minus_right = 0.0
        obs_left_minus_right = 0.0
        decided = 0
        correct = 0
        for row in test:
            prob = _choice_prob(fit_, coder, row)
            ll += -math.log(max(prob[row.choice], 1e-12))
            pred_left_minus_right += prob[0] - prob[1]
            if row.choice == 0:
                obs_left_minus_right += 1
                decided += 1
            elif row.choice == 1:
                obs_left_minus_right -= 1
                decided += 1
            predicted = int(np.argmax(prob[:2])) if row.choice != 2 else 2
            correct += int(predicted == row.choice)
        out.append(
            {
                "block": block,
                "n": len(test),
                "logloss": ll / len(test),
                "uniform_logloss": uniform,
                "predicted_left_minus_right": pred_left_minus_right / len(test),
                "observed_left_minus_right": (
                    obs_left_minus_right / decided if decided else float("nan")
                ),
                "top_choice_accuracy": correct / len(test),
                "majority_baseline": max(
                    sum(1 for r in test if r.choice == k) for k in range(3)
                )
                / len(test),
            }
        )
    return out


def leave_one_design_out(bundle: Bundle, resolve: str = "corrected") -> list[dict]:
    suite = fit_suite(bundle, resolve)
    coder = suite["coder"]
    obs = suite["obs"]
    designs = sorted({o.design for o in obs})
    out = []
    for design in designs:
        train = [o for o in obs if o.design != design]
        test = [o for o in obs if o.design == design]
        rows = [_obs_row(o) for o in train]
        fm = _fit_logit(coder, rows, "meaning", ridge=HOLDOUT_RIDGE)
        fh = _fit_logit(coder, rows, "hce", ridge=HOLDOUT_RIDGE)
        spec = test[0].spec
        pm = _predict(fm, coder, spec)
        ph = _predict(fh, coder, spec)
        obs_m = float(np.mean([o.meaning for o in test]))
        obs_h = float(np.mean([o.hce for o in test]))
        out.append(
            {
                "design": design,
                "pack": spec.pack,
                "n": len(test),
                "meaning_predicted": pm,
                "meaning_observed": obs_m,
                "meaning_error": pm - obs_m,
                "hce_predicted": ph,
                "hce_observed": obs_h,
                "hce_error": ph - obs_h,
                "pack_in_training": any(o.spec.pack == spec.pack for o in train),
            }
        )
    return out


def leave_one_pack_out(bundle: Bundle, resolve: str = "corrected") -> list[dict]:
    """Emphasise extrapolation: a pack with no training artwork cannot be predicted."""
    suite = fit_suite(bundle, resolve)
    coder = suite["coder"]
    obs = suite["obs"]
    packs = sorted({o.spec.pack for o in obs})
    out = []
    for pack in packs:
        train = [o for o in obs if o.spec.pack != pack]
        test = [o for o in obs if o.spec.pack == pack]
        if not test:
            continue
        spec = test[0].spec
        in_training_pack = spec.pack in {o.spec.pack for o in train}
        out.append(
            {
                "pack": pack,
                "n": len(test),
                "pack_in_training": in_training_pack,
                "estimable": in_training_pack,
                "note": (
                    "pack fixed effect estimated from training artwork"
                    if in_training_pack
                    else "no training artwork in this pack: prediction is extrapolation and should be refused"
                ),
            }
        )
    return out


def person_cross_validation(bundle: Bundle, resolve: str = "corrected", folds: int = 5, seed: int = 11) -> list[dict]:
    suite = fit_suite(bundle, resolve)
    coder = suite["coder"]
    obs = suite["obs"]
    persons = sorted({o.person for o in obs})
    rng = np.random.default_rng(seed)
    assignment = dict(zip(rng.permutation(persons), np.arange(len(persons)) % folds))
    output = []
    for outcome in ("meaning", "hce"):
        ll = brier = base_ll = base_brier = 0.0
        for fold in range(folds):
            train = [_obs_row(o) for o in obs if assignment[o.person] != fold]
            test = [o for o in obs if assignment[o.person] == fold]
            fit_ = _fit_logit(coder, train, outcome, ridge=HOLDOUT_RIDGE)
            base = float(np.mean([r[outcome] for r in train]))
            for o in test:
                pred = _predict(fit_, coder, o.spec)
                t = getattr(o, outcome)
                ll += _logloss(pred, t)
                brier += (pred - t) ** 2
                base_ll += _logloss(base, t)
                base_brier += (base - t) ** 2
        n = len(obs)
        output.append(
            {
                "outcome": outcome,
                "logloss": ll / n,
                "brier": brier / n,
                "baseline_logloss": base_ll / n,
                "baseline_brier": base_brier / n,
                "n": n,
            }
        )
    return output


# --------------------------------------------------------------------------- #
# local copies of the fitters that keep the module dependency-free of globals
# --------------------------------------------------------------------------- #
def _coder(bundle, resolve):
    from .core import coder_for

    return coder_for(bundle, resolve)


def _choices(bundle, resolve):
    from .core import choices

    return choices(bundle, resolve)


def _obs_row(o: Obs) -> dict:
    return {"person": o.person, "group": o.group, "spec": o.spec, "meaning": o.meaning, "hce": o.hce}


def _fit_choice(coder: Coder, rows: list[Choice]) -> Fit:
    from .core import fit_choice

    return fit_choice(coder, rows)


def _fit_logit(coder: Coder, rows: list[dict], outcome: str, ridge: float = 1e-6) -> Fit:
    from .core import fit_logit

    return fit_logit(coder, rows, outcome, ridge=ridge)


def _choice_prob(fit_: Fit, coder: Coder, row: Choice) -> np.ndarray:
    k = len(coder.names)
    delta = fit_.beta[k]
    v = np.array([delta + coder.vec(row.left) @ fit_.beta[:k], delta + coder.vec(row.right) @ fit_.beta[:k], 0.0])
    return np.exp(v - logsumexp(v))


def _predict(fit_: Fit, coder: Coder, spec) -> float:
    x = np.concatenate([[1.0], coder.vec(spec)])
    return float(expit(x @ fit_.beta))


def _logloss(p: float, y: int) -> float:
    p = min(max(p, 1e-12), 1 - 1e-12)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))
