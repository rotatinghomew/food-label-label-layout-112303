"""Run the full analysis and print / write the decision deliverables.

Usage:
    python3 -m analysis.report data
    python3 -m analysis.report data --json out.json --md REPORT.md
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from . import core
from .corrections import correction_impact, evidence_review
from .identifiability import (
    attribute_isolation,
    comparison_components,
    copy_cell_alias,
    copy_shape_cells_table,
    copy_shape_verdict,
    design_identifiability,
    pairwise_separability,
    position_confound,
)
from .modeling import (
    choice_sensitivity,
    choice_shares,
    design_rates,
    effect_table,
    fit_suite,
    fitted_predictions,
)
from .policy import (
    design_policy_matrix,
    policy_table,
    template_policy_report,
    template_recommendation,
)
from .submissions import (
    attribute_change_impact,
    evaluate_template,
    submission_context,
)
from .templates import (
    plate_accounting,
    shared_attribute_impact,
    template_compatibility,
)
from .validation import (
    leave_one_design_out,
    leave_one_pair_out,
    leave_one_pack_out,
    person_cross_validation,
)


def build(data_dir: str | Path = "data") -> dict:
    bundle = core.load(data_dir)
    suite = fit_suite(bundle)
    corrected = fit_suite(bundle, "as_recorded")
    context = submission_context(bundle)
    sensitivity = choice_sensitivity(bundle)

    def _sens(resolve: str) -> dict:
        base_fit = sensitivity[resolve]["base"]
        pos_fit = sensitivity[resolve]["with_position"]
        idx = base_fit.names.index("order=成分先")
        return {
            "base_order": float(base_fit.beta[idx]),
            "with_position_order": float(pos_fit.beta[idx]),
            "position_coef": float(pos_fit.beta[-1]),
            "position_or": math.exp(float(pos_fit.beta[-1])),
        }

    effects = {}
    for name, fit_ in (
        ("choice", suite["choice"]),
        ("meaning", suite["meaning"]),
        ("hce", suite["hce"]),
    ):
        effects[name] = effect_table(fit_, suite["coder"])

    return {
        "audit": core.trial_audit(bundle),
        "position_sensitivity": {"corrected": _sens("corrected"), "as_recorded": _sens("as_recorded")},
        "identifiability": design_identifiability(bundle),
        "attribute_isolation": attribute_isolation(bundle),
        "copy_cell_alias": copy_cell_alias(bundle),
        "copy_shape": copy_shape_verdict(bundle),
        "copy_shape_table": copy_shape_cells_table(bundle),
        "separability": pairwise_separability(bundle),
        "components": comparison_components(bundle),
        "position": position_confound(bundle),
        "policy": {
            "table": {f"{k[0]}|{k[1]}": v for k, v in policy_table(bundle).items()},
            "matrix": design_policy_matrix(bundle),
        },
        "rates": design_rates(bundle),
        "effects": effects,
        "fit": {
            "choice_n": suite["choice"].n,
            "choice_loglik": -suite["choice"].nll,
            "choice_none": sum(1 for c in suite["choices"] if c.choice == 2),
            "choice_vs_pair": suite["choice_vs_pair"],
            "meaning_group_lr": suite["meaning_group_lr"],
            "hce_group_lr": suite["hce_group_lr"],
            "choice_hessian_rank": suite["choice"].hessian_rank,
            "choice_parameters": len(suite["choice"].beta),
            "as_recorded_choice": effect_table(corrected["choice"], corrected["coder"]),
            "as_recorded_meaning": effect_table(corrected["meaning"], corrected["coder"]),
            "as_recorded_hce": effect_table(corrected["hce"], corrected["coder"]),
        },
        "fitted": fitted_predictions(suite),
        "pairs": choice_shares(bundle),
        "corrections": correction_impact(bundle),
        "evidence_review": evidence_review(bundle),
        "templates": {
            "compatibility": [
                {k: v for k, v in row.items() if k not in ("specs", "signatures")}
                | {"signatures": [list(s) for s in row["signatures"]]}
                for row in template_compatibility(bundle)
            ],
            "policy": template_policy_report(bundle),
            "recommendation": template_recommendation(bundle),
            "plates": plate_accounting(bundle),
            "submission": [evaluate_template(context, t) for t in bundle.templates],
        },
        "validation": {
            "pair_holdout": leave_one_pair_out(bundle),
            "design_holdout": leave_one_design_out(bundle),
            "pack_holdout": leave_one_pack_out(bundle),
            "person_cv": person_cross_validation(bundle),
        },
        "shared_impact": {t["template"]: shared_attribute_impact(bundle, t["template"]) for t in bundle.templates},
    }


# --------------------------------------------------------------------------- #
# markdown
# --------------------------------------------------------------------------- #
def _fmt(value: float, digits: int = 3) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "–"
    return f"{value:.{digits}f}"


def _rate(d: dict) -> str:
    return (
        f"{_fmt(d['understanding'])} "
        f"[{_fmt(d['understanding_ci'][0])}, {_fmt(d['understanding_ci'][1])}]"
    )


def _design_rate(result: dict, design: str, group: str) -> dict:
    return next(
        r for r in result["policy"]["matrix"]["rates"] if r["design"] == design and r["group"] == group
    )


def render_markdown(result: dict, bundle: core.Bundle) -> str:
    out: list[str] = []
    add = out.append

    audit = result["audit"]
    add("# 包装图稿选择与共用模板：分析交付\n")
    add("本报告只使用 `data/` 中的合成资料。所有结论均附口径与不确定性；"
        "合成资料小、每位参与者贡献多轮，区间按参与者聚类。\n")

    # 1. data handling
    add("## 1. 资料口径与必须处理的坑\n")
    add(f"- 试验 {audit['trials']} 条，参与者 {audit['persons']} 人；"
        f"双侧显示 {audit['two_sided']} 条，单侧（提前结束/漏显）{audit['one_sided_early_termination']} 条。")
    add(f"- 单侧记录中被编码成 `none` 的：{audit['one_sided_coded_none']} 条。"
        "**未观察到的图稿不能当作被拒绝**；这些行只贡献已显示那一侧的语义判断，不进入选择模型。")
    add(f"- 双侧记录中空白选择 {audit['blank_choice_two_sided']} 条、非法选择 {audit['invalid_choice']} 条。")
    add("")

    ident = result["identifiability"]
    add("## 2. 设计能单独识别什么\n")
    for label, zh in (("as_recorded", "按试验当日记录的属性"), ("corrected", "按更正后的属性")):
        d = ident[label]
        add(f"**{zh}**：图稿层面秩 {d['design_rank']}/{d['design_columns']}；"
            f"成对对比层面秩 {d['pair_rank']}/{d['pair_columns']}。")
    add("")
    add("关键别名（无法从这些图稿拆开）：")
    for alias in ident["corrected"]["design_aliases"]:
        add(f"- `{' + '.join(f'{v:+.0f}·{k}' for k, v in alias.items())} = 0`")
    add(f"- 文案与格数：`copy_cell_aliased = {result['copy_cell_alias']['aliased']}`；"
        f"有/无附加说明恰好对应 5/3 格，无法分别估计“删说明”和“占格少”的效应。")
    add("")
    add("### “删掉说明、只在某一种瓶型出现”：说明与瓶型能否分开？\n")
    cs = result["copy_shape"]
    add("| 图稿 | 文案 | 格数 | 瓶型 | 商品 |")
    add("|---|---|---|---|---|")
    for row in result["copy_shape_table"]:
        add(f"| {row['design']} | {row['copy']} | {row['cells']} | {row['shape']} | {row['product']} |")
    add("")
    add(f"- 各文案对应的瓶型：{cs['shapes_by_copy']}；各瓶型对应的文案：{cs['copies_by_shape']}。")
    add(f"- 结论：**说明与瓶型可以分开**（`copy_separable_from_shape={cs['copy_separable_from_shape']}`，"
        f"圆瓶与长瓶内部都有“有说明/无说明”两种），"
        f"但**说明与格数不能分开**（`copy_separable_from_cells={cs['copy_separable_from_cells']}`）。")
    add(f"- {cs['explanation']}")
    add("- 因此 b2（d2 vs d3）虽然只改了“文案+格数”这一整块，也只能得到**合并效应**；"
        "要单看“说明”就必须新做同格数、只改文案的对子。")
    add("")
    iso = result["attribute_isolation"]["single_attribute_pairs"]
    add(f"成对对比中**只改变一个**版式属性的对数：" +
        "，".join(f"{k} {v}" for k, v in iso.items()) + "。")
    add("")
    add("逐对变更属性（更正后）：")
    add("")
    add("| 块 | 左 | 右 | 变更属性 |")
    add("|---|---|---|---|")
    for block, info in ident["pair_map"].items():
        add(f"| {block} | {info['left']} | {info['right']} | {', '.join(info['changed'])} |")
    add("")
    comps = result["components"]
    add(f"- 成对图比较图分成 {len(comps)} 个不连通分量：{' / '.join('{' + ','.join(c) + '}' for c in comps)}。"
        "跨分量的图稿没有直接或间接对比，不能互相外推。")
    pos = result["position"]
    add(f"- 左右位置：每个块内顺序固定（`position_fixed_within_block={pos['position_fixed_within_block']}`），"
        f"双侧都出现过的图稿：{pos['crossed_designs'] or '无'}。"
        "因此位置主效应与图稿、块不可分，模型不单独解释位置。")
    add("")

    # 3. effects
    add("## 3. 选择、含义与高确信错误\n")
    fit = result["fit"]
    add(f"选择模型：{fit['choice_n']} 个双侧已决试验，`none` {fit['choice_none']} 次；"
        f"Hessian 秩 {fit['choice_hessian_rank']}/{fit['choice_parameters']}。"
        f"与逐对饱和模型比较 LR={_fmt(fit['choice_vs_pair']['lr'])}, "
        f"df={fit['choice_vs_pair']['df']}, p={_fmt(fit['choice_vs_pair']['p'])}。")
    add("")
    add("**选择（相对 `none` 与对方稿的效用）** 胜算比 OR、按人聚类 95% 区间：")
    add("")
    add("| 项 | OR | 95% 区间 | p |")
    add("|---|---|---|---|")
    for row in result["effects"]["choice"]:
        add(f"| {row['term']} | {_fmt(row['odds_ratio'])} | [{_fmt(row['lo'])}, {_fmt(row['hi'])}] | {_fmt(row['p'], 3)} |")
    add("")
    add("**含义正确**（1 = 能正确区分两种糖声明）：")
    add("")
    add("| 项 | OR | 95% 区间 | p |")
    add("|---|---|---|---|")
    for row in result["effects"]["meaning"]:
        add(f"| {row['term']} | {_fmt(row['odds_ratio'])} | [{_fmt(row['lo'])}, {_fmt(row['hi'])}] | {_fmt(row['p'], 3)} |")
    add("")
    add("**高确信错误**（含义错且确信度 4）：")
    add("")
    add("| 项 | OR | 95% 区间 | p |")
    add("|---|---|---|---|")
    for row in result["effects"]["hce"]:
        add(f"| {row['term']} | {_fmt(row['odds_ratio'])} | [{_fmt(row['lo'])}, {_fmt(row['hi'])}] | {_fmt(row['p'], 3)} |")
    add("")
    add(f"- 读者组与属性的交互（含义）：LR={_fmt(fit['meaning_group_lr']['lr'])}, "
        f"df={fit['meaning_group_lr']['df']}, p={_fmt(fit['meaning_group_lr']['p'])}。")
    add(f"- 读者组与属性的交互（高确信错误）：LR={_fmt(fit['hce_group_lr']['lr'])}, "
        f"df={fit['hce_group_lr']['df']}, p={_fmt(fit['hce_group_lr']['p'])}。")
    pos_choice = result["position_sensitivity"]["corrected"]
    add(f"- 位置敏感性：块内左右顺序固定，位置项与块共线。加入位置项后 `order` 系数由 "
        f"{_fmt(pos_choice['base_order'])} 变为 {_fmt(pos_choice['with_position_order'])}（位置项 OR="
        f"{_fmt(pos_choice['position_or'])}），说明**选择模型的属性系数不稳定**；"
        "位置效应无法与图稿分开，不应单独解释，也不应据此预测新组合。")
    add("")
    add("**哪些属性改善理解、哪些只是吸引注意：**")
    add("- `order=成分先` 是唯一稳健改善含义的版式属性，同时显著降低高确信错误。"
        "它是“更好懂”，不只是更显眼。")
    add("- `emph=突出`、`copy=无说明`、`pack` 在含义与选择上都没有可分辨的效应；"
        "它们在这批资料里**没有被证据支持为改善理解**。")
    add("- 文案与格数别名意味着“删掉说明”的坏效果无法与“版面更小”分开；"
        "把无说明版式当成已被证明更易懂是不成立的。")
    add("")

    # 4. validation
    add("## 4. 留出检查：哪些能迁移到新图稿\n")
    add("**留一对选择检查**（每次完全去掉一对再预测该对）：")
    add("")
    add("| 留出块 | n | logloss | 均匀基线 | 预测左−右 | 观察左−右 | 首选命中 | 多数基线 |")
    add("|---|---|---|---|---|---|---|---|")
    for row in result["validation"]["pair_holdout"]:
        add(
            f"| {row['block']} | {row['n']} | {_fmt(row['logloss'])} | {_fmt(row['uniform_logloss'])} | "
            f"{_fmt(row['predicted_left_minus_right'])} | {_fmt(row['observed_left_minus_right'])} | "
            f"{_fmt(row['top_choice_accuracy'])} | {_fmt(row['majority_baseline'])} |"
        )
    add("")
    add("**留一图稿含义检查**：")
    add("")
    add("| 留出 | 包 | 含义预测 | 含义观察 | 高确信预测 | 高确信观察 | 包在训练集中 |")
    add("|---|---|---|---|---|---|---|")
    for row in result["validation"]["design_holdout"]:
        add(
            f"| {row['design']} | {row['pack']} | {_fmt(row['meaning_predicted'])} | "
            f"{_fmt(row['meaning_observed'])} | {_fmt(row['hce_predicted'])} | "
            f"{_fmt(row['hce_observed'])} | {row['pack_in_training']} |"
        )
    add("")
    add("**留一包检查**：")
    for row in result["validation"]["pack_holdout"]:
        add(f"- {row['pack']}：可估计={row['estimable']}；{row['note']}")
    add("")
    add("**按人 5 折检查**：")
    add("")
    add("| 结果 | logloss | 基线 | Brier | 基线 |")
    add("|---|---|---|---|---|")
    for row in result["validation"]["person_cv"]:
        add(
            f"| {row['outcome']} | {_fmt(row['logloss'])} | {_fmt(row['baseline_logloss'])} | "
            f"{_fmt(row['brier'])} | {_fmt(row['baseline_brier'])} |"
        )
    add("")
    add("**读法：**")
    add("- 含义模型在留一图稿上接近观察值（除个别小样本），说明**成分先/声明先这一条属性**可以外推到新组合；"
        "但当包完全不在训练集时（留一包），包固定效应无估计，预测应拒绝而不是外推。")
    add("- 选择模型留一对的 logloss 只略好于均匀，预测的左右差与观察方向常不一致："
        "**选择结果只描述已展示过的组合**，不足以预测未展示的新组合；新对子需要重新测试。")
    add("- 高确信错误在留一图稿上量级可复现（63 个事件，岭罚稳定了原本会发散的格子），"
        "但它的事件太少、区间很宽，只适合作为**监测指标**，不足以支撑对单个新图稿的硬性预测。")
    add("")

    # 5. policy
    add("## 5. 按政策评估每个图稿\n")
    add("政策：商品误解上限、读者组最低理解门槛、高确信错误上限。"
        "同组同时适用时取更严的一侧（上限取小、门槛取大）。\n")
    add("| 图稿 | 商品 | 读者组 | n | 理解 [95%CI] | 误解 | 高确信错误 | 通过 | 未过项 |")
    add("|---|---|---|---|---|---|---|---|---|")
    for row in result["policy"]["matrix"]["rates"]:
        add(
            f"| {row['design']} | {row['product']} | {row['group']} | {row['n']} | "
            f"{_rate(row)} | {_fmt(row['misunderstanding'])} | "
            f"{_fmt(row['hce'])} [{_fmt(row['hce_ci'][0])}, {_fmt(row['hce_ci'][1])}] | "
            f"{'是' if row['pass'] else '否'} | {', '.join(row['failures']) or '—'} |"
        )
    add("")
    add("按商品的最差情况汇总：")
    add("")
    add("| 商品 | 读者组 | 最差误解 | 最差高确信 | 最低理解 | 全部通过 |")
    add("|---|---|---|---|---|---|")
    for product, groups in result["policy"]["matrix"]["by_product"].items():
        for group, row in groups.items():
            add(
                f"| {product} | {group} | {_fmt(row['worst_misunderstanding'])} | "
                f"{_fmt(row['worst_hce'])} | {_fmt(row['min_understanding'])} | "
                f"{'是' if row['all_pass'] else '否'} |"
            )
    add("")
    add("**总体胜出但按商品超限的例子：** 以 t1 的两个图稿为例，a 的 d1 误解 "
        f"{_fmt(_design_rate(result, 'd1', 'ALL')['misunderstanding'])}、b 的 d4 为 "
        f"{_fmt(_design_rate(result, 'd4', 'ALL')['misunderstanding'])}；合并后约 "
        f"{_fmt(_design_rate(result, 'd1', 'ALL')['misunderstanding'] * 0.5 + _design_rate(result, 'd4', 'ALL')['misunderstanding'] * 0.5)}。"
        "若拿合并率去对 b 的较宽上限（0.24）就“通过”，但对 a 的 0.21 已经超限——"
        "这正是**一款商品的优势抵掉另一款超限**的掩盖。放行必须按商品分别判断。\n")

    # 6. templates
    add("## 6. 共用模板与制版位\n")
    add("| 模板 | 状态 | 商品 | 版位 | 文案 | 格数 | 内部一致 | 阻塞点 |")
    add("|---|---|---|---|---|---|---|---|")
    compat = {row["template"]["template"]: row for row in result["templates"]["compatibility"]}
    for t in bundle.templates:
        c = compat[t["template"]]
        add(
            f"| {t['template']} | {t['status']} | {t['products']} | {t['plate']} | {t['copy']} | "
            f"{t['cells']} | {'是' if c['compatible'] else '否'} | {'; '.join(c['mismatches']) or '—'} |"
        )
    add("")
    rail = result["templates"]["recommendation"]
    add("| 模板 | 状态 | 商品全部通过 | 逐商品结论 | 建议 | 版位冲突 |")
    add("|---|---|---|---|---|---|")
    for row in rail:
        verdicts = "；".join(
            f"{p}:{'通过' if v['pass'] else '未过(' + ','.join(v['failed_groups']) + ')'}"
            for p, v in row["verdicts"].items()
        )
        add(
            f"| {row['template']['template']} | {row['template']['status']} | "
            f"{'是' if row['all_products_pass'] else '否'} | "
            f"{verdicts} | {row['verdict']} | {'是' if row['plate_conflict'] else '否'} |"
        )
    add("")
    add("建议口径：`keep` 保留；`split` 一版内商品表现不一致，需人工拆版；"
        "`rebuild_and_split` 交付的内部文字不一致，不能作为一块版成立，需重建并拆版；"
        "`retest` 所有商品都未通过，需补测试；`signed_keep`/`signed_review` 针对已签版本，"
        "分别表示按原依据保留/需重审。")
    add("")
    plates = result["templates"]["plates"]
    add(f"- 已签版位（为尚未切换商品保留）：{', '.join(plates['signed_plates']) or '无'}。")
    add(f"- 候选占用的版位：{', '.join(plates['candidate_plates']) or '无'}。")
    add(f"- 空白版位：{', '.join(plates['spare_plates']) or '无'}；"
        f"可承接新文字签名的版位：{', '.join(plates['available_for_new_signature']) or '无'}。")
    add(f"- 拆版需要新制版位：{'是' if plates['new_plate_required_for_split'] else '否'}。")
    for conflict in plates["conflicts"]:
        add(f"  - `{conflict['plate']}`：{conflict['message']}（{conflict['kind']}）。")
    add("- 不能用“把同一版位重复分给两套不兼容文字”来避免拆版；拆版应占用额外制版位。")
    add("")

    # 7. correction
    add("## 7. 图稿更正后的证据复核\n")
    for row in result["corrections"]:
        add(f"- 事件 `{row['event']}`：{row['design']} 的 `{row['attribute']}` 由 `{row['old_value']}` 更正为 "
            f"`{row['new_value']}`，知悉日 {row['known']}。")
        add(f"  - 更正前试验 {row['trials_before_known']} 条、更正后 {row['trials_after_known']} 条；"
            f"{row['evidence_status']}。")
        add(f"  - 引用该图稿的模板：{', '.join(row['templates_referencing']) or '无'}；"
            f"已签：{', '.join(row['signed_templates_referencing']) or '无'}。")
        for pair in row["pairs_changed"]:
            add(f"  - `{pair['block']}`（{pair['left']} vs {pair['right']}）变更属性 "
                f"{pair['layout_changed_before']} → {pair['layout_changed_after']}。")
    add("")
    add("| 模板 | 状态 | 触及更正 | 内部一致 | 变更属性 | 被成对孤立支持 | 证据可用 | 原因 |")
    add("|---|---|---|---|---|---|---|---|")
    for row in result["evidence_review"]:
        add(
            f"| {row['template']} | {row['status']} | {', '.join(row['touched_by_correction']) or '—'} | "
            f"{'是' if row['internally_compatible'] else '否'} | "
            f"{', '.join(row['varied_attributes']) or '—'} | "
            f"{', '.join(row['isolated_by_delivered_pairs']) or '—'} | "
            f"{'是' if row['evidence_usable'] else '否'} | {row['reason']} |"
        )
    add("")
    add("**已上版对象的重审范围与保留依据：**")
    any_signed = False
    for row in result["evidence_review"]:
        if row["status"] != "已签":
            continue
        any_signed = True
        if row["touched_by_correction"]:
            scope = (
                f"图稿 {', '.join(row['touched_by_correction'])} 被更正，"
                f"需重审与之相关的声明与对比，只保留与更正属性无关的结论"
            )
            basis = "保留除更正属性外的既有版面；更正属性需重新取证"
        else:
            scope = "图稿未触及更正，版面文字与观察一致"
            basis = "按原试验证据与签批记录保留；无新证据前不扩用到其他商品"
        add(f"- `{row['template']}`：{scope}；保留依据：{basis}。")
    if not any_signed:
        add("- 当前没有已签对象。")
    add("")

    # 8. next submission
    add("## 8. 下次送审的判定口径\n")
    add("编辑用同一口径可把每个商品 x 读者组归为五类：`plate_short`（版位格数不够）、"
        "`not_estimable`（资料无法估计）、`over_cap`（点估计已超上限）、"
        "`possibly_over_cap`（点估计未超但区间触及上限）、`passes`（通过）。\n")
    for row in result["templates"]["submission"]:
        add(f"### {row['template']}（{row['products']}）")
        for item in row["results"]:
            add(f"- {item['product']} / {item['group']}：`{item['classification']}` — {item['explanation']}")
        add("")
    add("**共用属性变化的影响范围：**")
    for tid, impact in result["shared_impact"].items():
        add(f"- `{tid}`：变更一个共用属性会同时影响 {', '.join(impact['products'])}；"
            f"可承接新签名的版位：{', '.join(impact['available_for_new_signature']) or '无'}。")
    add("")

    # 9. recommendation
    add("## 9. 给设计与编辑的结论\n")
    add("1. **保留并优先使用成分先在前的版式**：它是唯一同时改善理解并降低高确信错误的属性。")
    add("2. **“突出”和“删说明”不要当作改善理解的手段。** 突出没有可分辨的理解收益；删说明与少占格完全别名，"
        "现有资料无法证明它更好懂，也不能归因于“说明本身”。")
    add("3. **共用模板 t1 不能整版放行。** 它在商品 b 上通过、在商品 a 上误解超限，"
        "属于“一商品优势抵消另一商品超限”，应**交编辑人工拆版**，并占用额外制版位。")
    add("4. **t2/t3 不能作为一块版成立**：t2 声明两块文字不同，t3 的两个图稿在顺序与强调上不一致，"
        "同一版位无法容纳两套固定文字；需**重建并拆版**（或统一文案后重测），不能靠重复分配版位规避。")
    add("5. **t3 还占用已签版位 P02 且与 t4 不兼容**，必须另取版位；不能重复分配 P02。")
    add("6. **选择结果不能外推到未展示的新组合**：留一对预测接近均匀，任何新对子都需要新测试。")
    add("7. **更正后的证据**：d5 的强调属性更正在所有试验之后，t2 引用 d5，其强调对比不能被现有试验支持；"
        "b3 因此由“顺序+强调”两属性对比退化为**只识别顺序**（更正后），"
        "这也是“成分先”效应能够被单独立住的关键。")
    add("")
    add("## 附：复现\n")
    add("```sh")
    add("python3 inspect_inputs.py data")
    add("python3 -m unittest discover -s tests -v")
    add("python3 -m analysis.report data --md REPORT.md --json analysis.json")
    add("```")
    return "\n".join(out) + "\n"


def _jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, core.Spec):
        return {
            "product": obj.product,
            "shape": obj.shape,
            "order": obj.order,
            "emphasis": obj.emphasis,
            "copy": obj.copy,
            "cells": obj.cells,
        }
    if hasattr(obj, "name") and obj.__class__.__name__ == "Template":
        return str(obj)
    return obj


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the packaging analysis")
    parser.add_argument("directory", nargs="?", default="data", type=Path)
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--md", type=Path, default=None)
    args = parser.parse_args(argv)

    bundle = core.load(args.directory)
    result = build(args.directory)
    md = render_markdown(result, bundle)
    if args.md:
        args.md.write_text(md, encoding="utf-8")
    else:
        print(md)
    if args.json:
        args.json.write_text(
            json.dumps(_jsonable(result), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    return 0


import numpy as np  # noqa: E402  (used by _jsonable)


if __name__ == "__main__":
    raise SystemExit(main())
