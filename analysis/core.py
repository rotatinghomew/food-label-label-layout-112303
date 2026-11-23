"""Core data loading, coding and cluster-robust estimation.

Modelling decisions that matter for the conclusions
---------------------------------------------------
* **Attribute resolution is date-aware.**  A correction in ``corrections.csv``
  has a ``known`` date.  Trials fielded before that date were run on the
  artwork as it then existed, so the *primary* design-effect model uses the
  corrected attribute values (the correction states what the artwork actually
  was), while ``resolve="as_recorded"`` reproduces the metadata as it stood on
  each trial day.  All trials here predate the only correction, so the two
  views differ exactly on ``d5``'s emphasis.
* **One-sided trials are early terminations**, not ``none`` choices.  They are
  excluded from the choice model and contribute only their shown side to the
  comprehension model.
* **Pack fixed effects** are product x shape.  With one design per pack (or one
  level per pack) shape and product main effects cannot be separated from the
  pack, so the pack absorbs them.
* **Uncertainty is clustered by person**: each person contributes several
  choices and several comprehension tickets, so naive standard errors would be
  too narrow.
"""
from __future__ import annotations

import csv
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, logsumexp

ATTRS = ("order", "emphasis", "copy")
COPY_VALUES = ("未加蔗糖说明", "无附加说明")
FUTURE = "9999-12-31"
RESOLVE_MODES = ("corrected", "as_recorded")


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #
def _rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, strict=True))


def _slash(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split("/") if part.strip())


@dataclass(frozen=True)
class Spec:
    """A concrete artwork specification."""

    product: str
    shape: str
    order: str
    emphasis: str
    copy: str
    cells: int

    @property
    def pack(self) -> str:
        return f"{self.product}-{self.shape}"

    @property
    def copy_bundle(self) -> tuple[str, int]:
        """Copy text and cell requirement travel together and are aliased."""
        return (self.copy, self.cells)

    def key(self) -> tuple:
        return (self.pack, self.order, self.emphasis, self.copy, self.cells)


@dataclass
class Bundle:
    designs: dict[str, dict]
    corrections: list[dict]
    blocks: dict[str, dict]
    trials: list[dict]
    templates: list[dict]
    policy: list[dict]
    data_dir: Path = field(default=Path("data"))

    # -- attribute resolution ------------------------------------------------
    def attrs_at(self, design: str, day: str = FUTURE) -> dict:
        base = dict(self.designs[design])
        for correction in self.corrections:
            if correction["design"] != design:
                continue
            if correction["known"] <= day:
                base[correction["attribute"]] = correction["new_value"]
        return base

    def spec_at(self, design: str, day: str = FUTURE) -> Spec:
        attrs = self.attrs_at(design, day)
        return Spec(
            product=attrs["product"],
            shape=attrs["shape"],
            order=attrs["order"],
            emphasis=attrs["emphasis"],
            copy=attrs["copy"],
            cells=int(attrs["required_cells"]),
        )

    def corrected_spec(self, design: str) -> Spec:
        return self.spec_at(design, FUTURE)

    def displayed_spec(self, design: str, day: str) -> Spec:
        """Metadata as it stood on the trial day."""
        return self.spec_at(design, day)

    def resolved_spec(self, design: str, day: str, resolve: str) -> Spec:
        if resolve == "corrected":
            return self.corrected_spec(design)
        if resolve == "as_recorded":
            return self.displayed_spec(design, day)
        raise ValueError(f"resolve must be one of {RESOLVE_MODES}")

    # -- templates -----------------------------------------------------------
    def template_specs(self, template: dict) -> list[Spec]:
        return [self.corrected_spec(d) for d in _slash(template["designs"])]

    def template_products(self, template: dict) -> tuple[str, ...]:
        return _slash(template["products"])

    def template_shapes(self, template: dict) -> tuple[str, ...]:
        return _slash(template["shape"])

    def template_cells(self, template: dict) -> int:
        return int(template["cells"])

    def template_copy(self, template: dict) -> str:
        return template["copy"]

    def signed(self) -> list[dict]:
        return [t for t in self.templates if t["status"] == "已签"]

    def candidates(self) -> list[dict]:
        return [t for t in self.templates if t["status"] != "已签"]


def load(data_dir: str | Path = "data") -> Bundle:
    directory = Path(data_dir)
    designs_rows = _rows(directory / "designs.csv")
    block_rows = _rows(directory / "blocks.csv")
    designs = {r["design"]: r for r in designs_rows}
    blocks = {r["block"]: r for r in block_rows}
    if len(designs) != len(designs_rows):
        raise ValueError("designs.csv has duplicate design ids")
    if len(blocks) != len(block_rows):
        raise ValueError("blocks.csv has duplicate block ids")
    return Bundle(
        designs=designs,
        corrections=_rows(directory / "corrections.csv"),
        blocks=blocks,
        trials=_rows(directory / "trials.csv"),
        templates=_rows(directory / "templates.csv"),
        policy=_rows(directory / "policy.csv"),
        data_dir=directory,
    )


# --------------------------------------------------------------------------- #
# observations
# --------------------------------------------------------------------------- #
@dataclass
class Obs:
    person: str
    group: str
    design: str
    spec: Spec
    day: str
    block: str
    side: str
    truncated: bool
    meaning: int
    confidence: int
    chosen: bool

    @property
    def hce(self) -> int:
        return int(self.meaning == 0 and self.confidence == 4)


def observations(bundle: Bundle, resolve: str = "corrected") -> list[Obs]:
    """One row per shown artwork side with a recorded meaning judgement."""
    out: list[Obs] = []
    for row in bundle.trials:
        truncated = not (row["shown_left"] and row["shown_right"])
        for side in ("left", "right"):
            design = row["shown_" + side]
            if not design:
                continue
            if row["meaning_" + side] == "" or row["confidence_" + side] == "":
                continue
            out.append(
                Obs(
                    person=row["person"],
                    group=row["group"],
                    design=design,
                    spec=bundle.resolved_spec(design, row["day"], resolve),
                    day=row["day"],
                    block=row["block"],
                    side=side,
                    truncated=truncated,
                    meaning=int(row["meaning_" + side]),
                    confidence=int(row["confidence_" + side]),
                    chosen=row["choice"] == design,
                )
            )
    return out


@dataclass
class Choice:
    person: str
    group: str
    block: str
    left: Spec
    right: Spec
    choice: int  # 0 left, 1 right, 2 none
    left_design: str
    right_design: str


def choices(bundle: Bundle, resolve: str = "corrected") -> list[Choice]:
    """Decided, two-sided trials only.

    A row with a missing side is an early termination and is never coded as a
    ``none`` rejection of an artwork the participant did not see.
    """
    out: list[Choice] = []
    for row in bundle.trials:
        left, right = row["shown_left"], row["shown_right"]
        if not (left and right):
            continue
        if row["choice"] == left:
            pick = 0
        elif row["choice"] == right:
            pick = 1
        elif row["choice"] == "none":
            pick = 2
        else:
            continue
        out.append(
            Choice(
                person=row["person"],
                group=row["group"],
                block=row["block"],
                left=bundle.resolved_spec(left, row["day"], resolve),
                right=bundle.resolved_spec(right, row["day"], resolve),
                choice=pick,
                left_design=left,
                right_design=right,
            )
        )
    return out


def trial_audit(bundle: Bundle) -> dict:
    """Counts behind the handling of missing displays and invalid choices."""
    two_sided = 0
    one_sided = 0
    blank_two_sided = 0
    invalid_choice = 0
    one_sided_not_none = 0
    for row in bundle.trials:
        left, right = row["shown_left"], row["shown_right"]
        if left and right:
            two_sided += 1
            if not row["choice"]:
                blank_two_sided += 1
            elif row["choice"] not in (left, right, "none"):
                invalid_choice += 1
        else:
            one_sided += 1
            if row["choice"] == "none":
                one_sided_not_none += 1
    return {
        "trials": len(bundle.trials),
        "persons": len({row["person"] for row in bundle.trials}),
        "two_sided": two_sided,
        "one_sided_early_termination": one_sided,
        "blank_choice_two_sided": blank_two_sided,
        "invalid_choice": invalid_choice,
        "one_sided_coded_none": one_sided_not_none,
    }


# --------------------------------------------------------------------------- #
# coding
# --------------------------------------------------------------------------- #
class Coder:
    """Pack fixed effects plus the three layout attributes."""

    def __init__(self, packs: list[str]):
        if not packs:
            raise ValueError("no packs")
        self.packs = sorted(set(packs))
        self.ref = self.packs[0]
        self.names = [f"pack:{p}" for p in self.packs[1:]] + [
            "order=成分先",
            "emph=突出",
            "copy=无说明",
        ]

    def vec(self, spec: Spec) -> np.ndarray:
        return np.array(
            [1.0 if spec.pack == p else 0.0 for p in self.packs[1:]]
            + [
                1.0 if spec.order == "成分先" else 0.0,
                1.0 if spec.emphasis == "突出" else 0.0,
                1.0 if spec.copy == "无附加说明" else 0.0,
            ],
            dtype=float,
        )

    def row(self, spec: Spec) -> np.ndarray:
        return np.concatenate([[1.0], self.vec(spec)])

    @property
    def intercept_names(self) -> list[str]:
        return ["intercept"] + self.names

    def has_pack(self, spec: Spec) -> bool:
        return spec.pack in self.packs


def coder_for(bundle: Bundle, resolve: str = "corrected") -> Coder:
    packs = {bundle.resolved_spec(d, FUTURE, resolve).pack for d in bundle.designs}
    return Coder(sorted(packs))


# --------------------------------------------------------------------------- #
# estimation helpers
# --------------------------------------------------------------------------- #
@dataclass
class Fit:
    names: list[str]
    beta: np.ndarray
    cov: np.ndarray
    nll: float
    n: int
    events: int | None = None
    hessian_rank: int | None = None
    group_main: bool = False
    group_inter: tuple[str, ...] = ()
    include_attributes: bool = True

    @property
    def se(self) -> np.ndarray:
        return np.sqrt(np.clip(np.diag(self.cov), 0.0, np.inf))

    def as_dict(self) -> dict:
        out = {}
        for name, beta, se in zip(self.names, self.beta, self.se):
            out[name] = {
                "coef": float(beta),
                "se": float(se),
                "odds_ratio": float(math.exp(beta)) if abs(beta) < 50 else float("inf"),
            }
        return out


def _hessian(func, x: np.ndarray, eps: float = 1e-5) -> np.ndarray:
    n = len(x)
    out = np.zeros((n, n))
    for i in range(n):
        for j in range(i, n):
            ei = np.zeros(n)
            ei[i] = eps
            ej = np.zeros(n)
            ej[j] = eps
            out[i, j] = out[j, i] = (
                func(x + ei + ej)
                - func(x + ei - ej)
                - func(x - ei + ej)
                + func(x - ei - ej)
            ) / (4 * eps * eps)
    return out


def _sandwich(scores: dict[str, np.ndarray], hessian: np.ndarray) -> np.ndarray:
    information = np.linalg.pinv(hessian)
    meat = sum(np.outer(s, s) for s in scores.values())
    return information @ meat @ information


def _group_terms(names: list[str], spec: Spec, coder: Coder, group: str) -> list[float]:
    old = 1.0 if group == "老读者" else 0.0
    values: list[float] = []
    for name in names:
        if name == "old_reader":
            values.append(old)
        elif name.startswith("old_reader_x_"):
            attr = name.removeprefix("old_reader_x_")
            values.append(old * coder.vec(spec)[coder.names.index(attr)])
        else:
            raise ValueError(f"unknown extra term {name}")
    return values


def fit_logit(
    coder: Coder,
    rows: list[dict],
    outcome: str,
    *,
    group_main: bool = False,
    group_inter: tuple[str, ...] = (),
    ridge: float = 1e-6,
) -> Fit:
    """Bernoulli logit for a comprehension outcome, clustered by person."""
    names = list(coder.intercept_names)
    extra: list[str] = []
    if group_main:
        extra.append("old_reader")
    for attr in group_inter:
        if attr not in coder.names:
            raise ValueError(f"unknown interaction attribute {attr}")
        extra.append(f"old_reader_x_{attr}")

    def build(spec: Spec, group: str) -> np.ndarray:
        values = [1.0] + list(coder.vec(spec)) + _group_terms(extra, spec, coder, group)
        return np.asarray(values, dtype=float)

    X = np.vstack([build(r["spec"], r["group"]) for r in rows])
    y = np.asarray([r[outcome] for r in rows], dtype=float)
    p = X.shape[1]

    def nll(beta: np.ndarray) -> float:
        z = X @ beta
        return float(np.sum(np.logaddexp(0.0, z) - y * z) + 0.5 * ridge * np.sum(beta[1:] ** 2))

    def grad(beta: np.ndarray) -> np.ndarray:
        z = X @ beta
        g = X.T @ (expit(z) - y)
        g[1:] += ridge * beta[1:]
        return g

    res = minimize(
        nll,
        np.zeros(p),
        jac=grad,
        method="L-BFGS-B",
        options={"maxiter": 5000, "ftol": 1e-14, "gtol": 1e-10},
    )
    beta = res.x
    hessian = _hessian(nll, beta)
    mu = expit(X @ beta)
    scores: dict[str, np.ndarray] = defaultdict(lambda: np.zeros(p))
    for index, row in enumerate(rows):
        scores[row["person"]] += X[index] * (y[index] - mu[index])
    return Fit(
        names=names + extra,
        beta=beta,
        cov=_sandwich(scores, hessian),
        nll=float(res.fun),
        n=len(rows),
        events=int(y.sum()),
        hessian_rank=int(np.linalg.matrix_rank(hessian)),
        group_main=group_main,
        group_inter=group_inter,
    )


def fit_choice(
    coder: Coder,
    rows: list[Choice],
    *,
    include_position: bool = False,
    include_attributes: bool = True,
    ridge: float = 1e-6,
) -> Fit:
    """Conditional logit over {left, right, none}, clustered by person."""
    k = len(coder.names)
    p = k + 1 + (1 if include_position else 0)

    def design_vec(spec: Spec) -> np.ndarray:
        return coder.vec(spec) if include_attributes else np.zeros(k)

    def utilities(row: Choice, beta: np.ndarray) -> np.ndarray:
        delta = beta[k]
        position = beta[k + 1] if include_position else 0.0
        left = delta + design_vec(row.left) @ beta[:k] + position
        right = delta + design_vec(row.right) @ beta[:k]
        return np.array([left, right, 0.0])

    def nll(beta: np.ndarray) -> float:
        total = 0.0
        for row in rows:
            v = utilities(row, beta)
            total += v[row.choice] - logsumexp(v)
        return -total + 0.5 * ridge * np.sum(beta[:k] ** 2)

    def grad(beta: np.ndarray) -> np.ndarray:
        g = np.zeros(p)
        for row in rows:
            v = utilities(row, beta)
            prob = np.exp(v - logsumexp(v))
            d = np.zeros(3)
            d[row.choice] = 1.0
            d -= prob
            g[:k] += d[0] * design_vec(row.left) + d[1] * design_vec(row.right)
            g[k] += d[0] + d[1]
            if include_position:
                g[k + 1] += d[0]
        # g currently accumulates the log-likelihood score; nll has the ridge.
        out = -g
        out[:k] += ridge * beta[:k]
        return out

    res = minimize(
        nll,
        np.zeros(p),
        jac=grad,
        method="L-BFGS-B",
        options={"maxiter": 5000, "ftol": 1e-14, "gtol": 1e-10},
    )
    beta = res.x
    hessian = _hessian(nll, beta)
    scores: dict[str, np.ndarray] = defaultdict(lambda: np.zeros(p))
    for row in rows:
        v = utilities(row, beta)
        prob = np.exp(v - logsumexp(v))
        d = np.zeros(3)
        d[row.choice] = 1.0
        d -= prob
        s = np.zeros(p)
        s[:k] = d[0] * design_vec(row.left) + d[1] * design_vec(row.right)
        s[k] = d[0] + d[1]
        if include_position:
            s[k + 1] = d[0]
        scores[row.person] += s
    names = (list(coder.names) if include_attributes else []) + ["design_vs_none"]
    if include_position:
        names.append("left_position")
    return Fit(
        names=names,
        beta=beta,
        cov=_sandwich(scores, hessian),
        nll=float(res.fun),
        n=len(rows),
        hessian_rank=int(np.linalg.matrix_rank(hessian)),
        include_attributes=include_attributes,
    )


def fit_pair_fe(rows: list[Choice]) -> Fit:
    """Saturated per-pair utilities (two free utilities per pair, none = 0)."""
    blocks = sorted({row.block for row in rows})
    index = {block: i for i, block in enumerate(blocks)}
    p = 2 * len(blocks)

    def utilities(row: Choice, beta: np.ndarray) -> np.ndarray:
        i = index[row.block]
        return np.array([beta[2 * i], beta[2 * i + 1], 0.0])

    def nll(beta: np.ndarray) -> float:
        total = 0.0
        for row in rows:
            v = utilities(row, beta)
            total += v[row.choice] - logsumexp(v)
        return -total

    def grad(beta: np.ndarray) -> np.ndarray:
        g = np.zeros(p)
        for row in rows:
            v = utilities(row, beta)
            prob = np.exp(v - logsumexp(v))
            d = np.zeros(3)
            d[row.choice] = 1.0
            d -= prob
            i = index[row.block]
            g[2 * i] += d[0]
            g[2 * i + 1] += d[1]
        return -g

    res = minimize(
        nll,
        np.zeros(p),
        jac=grad,
        method="L-BFGS-B",
        options={"maxiter": 5000, "ftol": 1e-14, "gtol": 1e-10},
    )
    return Fit(names=[f"pair:{b}" for b in blocks], beta=res.x, cov=np.zeros((p, p)), nll=float(res.fun), n=len(rows))


def lr_test(small: Fit, large: Fit) -> dict:
    statistic = max(0.0, 2.0 * (small.nll - large.nll))
    df = len(large.beta) - len(small.beta)
    if df <= 0:
        raise ValueError("large model must nest small model")
    from scipy.stats import chi2

    return {"lr": statistic, "df": df, "p": float(1.0 - chi2.cdf(statistic, df))}


# --------------------------------------------------------------------------- #
# prediction
# --------------------------------------------------------------------------- #
def predict_logit(fit: Fit, coder: Coder, spec: Spec, group: str = "普通读者") -> dict:
    extra = (["old_reader"] if fit.group_main else []) + [
        f"old_reader_x_{a}" for a in fit.group_inter
    ]
    values = [1.0] + list(coder.vec(spec)) + _group_terms(extra, spec, coder, group)
    x = np.asarray(values, dtype=float)
    eta = float(x @ fit.beta)
    prob = float(expit(eta))
    grad = prob * (1.0 - prob) * x
    se = float(np.sqrt(max(0.0, grad @ fit.cov @ grad)))
    return {"prob": prob, "se": se, "lo": float(expit(eta - 1.96 * se)), "hi": float(expit(eta + 1.96 * se))}


def predict_choice_share(fit: Fit, coder: Coder, left: Spec, right: Spec) -> dict:
    """Predicted {left, right, none} shares with delta-method standard errors."""
    k = len(coder.names)
    include_attributes = fit.include_attributes

    def shares(beta: np.ndarray) -> np.ndarray:
        delta = beta[k]
        position = beta[k + 1] if len(beta) > k + 1 else 0.0
        lv = coder.vec(left) @ beta[:k] if include_attributes else 0.0
        rv = coder.vec(right) @ beta[:k] if include_attributes else 0.0
        v = np.array([delta + lv + position, delta + rv, 0.0])
        return np.exp(v - logsumexp(v))

    base = shares(fit.beta)
    jac = np.zeros((3, len(fit.beta)))
    eps = 1e-6
    for j in range(len(fit.beta)):
        plus = fit.beta.copy()
        minus = fit.beta.copy()
        plus[j] += eps
        minus[j] -= eps
        jac[:, j] = (shares(plus) - shares(minus)) / (2 * eps)
    var = np.einsum("ij,jk,ik->i", jac, fit.cov, jac)
    se = np.sqrt(np.clip(var, 0.0, np.inf))
    return {
        "left": {"share": float(base[0]), "se": float(se[0])},
        "right": {"share": float(base[1]), "se": float(se[1])},
        "none": {"share": float(base[2]), "se": float(se[2])},
    }
