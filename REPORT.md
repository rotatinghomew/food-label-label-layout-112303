# 包装图稿选择与共用模板：分析交付

本报告只使用 `data/` 中的合成资料。所有结论均附口径与不确定性；合成资料小、每位参与者贡献多轮，区间按参与者聚类。

## 1. 资料口径与必须处理的坑

- 试验 384 条，参与者 96 人；双侧显示 363 条，单侧（提前结束/漏显）21 条。
- 单侧记录中被编码成 `none` 的：0 条。**未观察到的图稿不能当作被拒绝**；这些行只贡献已显示那一侧的语义判断，不进入选择模型。
- 双侧记录中空白选择 0 条、非法选择 0 条。

## 2. 设计能单独识别什么

**按试验当日记录的属性**：图稿层面秩 7/8；成对对比层面秩 5/8。
**按更正后的属性**：图稿层面秩 7/8；成对对比层面秩 5/8。

关键别名（无法从这些图稿拆开）：
- `-1·copy=无说明 + +1·cells=3 = 0`
- 文案与格数：`copy_cell_aliased = True`；有/无附加说明恰好对应 5/3 格，无法分别估计“删说明”和“占格少”的效应。

### “删掉说明、只在某一种瓶型出现”：说明与瓶型能否分开？

| 图稿 | 文案 | 格数 | 瓶型 | 商品 |
|---|---|---|---|---|
| d1 | 未加蔗糖说明 | 5 | 圆 | a |
| d2 | 未加蔗糖说明 | 5 | 圆 | a |
| d3 | 无附加说明 | 3 | 圆 | a |
| d4 | 未加蔗糖说明 | 5 | 方 | b |
| d5 | 未加蔗糖说明 | 5 | 方 | b |
| d6 | 未加蔗糖说明 | 5 | 长 | b |
| d7 | 无附加说明 | 3 | 长 | c |
| d8 | 未加蔗糖说明 | 5 | 长 | c |

- 各文案对应的瓶型：{'无附加说明': ['圆', '长'], '未加蔗糖说明': ['圆', '方', '长']}；各瓶型对应的文案：{'圆': ['无附加说明', '未加蔗糖说明'], '方': ['未加蔗糖说明'], '长': ['无附加说明', '未加蔗糖说明']}。
- 结论：**说明与瓶型可以分开**（`copy_separable_from_shape=True`，圆瓶与长瓶内部都有“有说明/无说明”两种），但**说明与格数不能分开**（`copy_separable_from_cells=False`）。
- 删说明与少占格完全别名（无说明=3 格，有说明=5 格），不能分别估计；文案在部分瓶型内变化，可与瓶型分开；无说明版只出现在瓶型 圆/长。
- 因此 b2（d2 vs d3）虽然只改了“文案+格数”这一整块，也只能得到**合并效应**；要单看“说明”就必须新做同格数、只改文案的对子。

成对对比中**只改变一个**版式属性的对数：order 1，emphasis 0，copy 0，cells 0。

逐对变更属性（更正后）：

| 块 | 左 | 右 | 变更属性 |
|---|---|---|---|
| b1 | d1 | d2 | order, emphasis |
| b2 | d2 | d3 | copy, cells |
| b3 | d4 | d5 | order |
| b4 | d5 | d6 | pack |
| b5 | d6 | d8 | order, emphasis, pack |
| b6 | d7 | d8 | order, emphasis, copy, cells |

- 成对图比较图分成 2 个不连通分量：{d1,d2,d3} / {d4,d5,d6,d7,d8}。跨分量的图稿没有直接或间接对比，不能互相外推。
- 左右位置：每个块内顺序固定（`position_fixed_within_block=True`），双侧都出现过的图稿：['d8']。因此位置主效应与图稿、块不可分，模型不单独解释位置。

## 3. 选择、含义与高确信错误

选择模型：363 个双侧已决试验，`none` 34 次；Hessian 秩 7/7。与逐对饱和模型比较 LR=6.327, df=5, p=0.276。

**选择（相对 `none` 与对方稿的效用）** 胜算比 OR、按人聚类 95% 区间：

| 项 | OR | 95% 区间 | p |
|---|---|---|---|
| pack:b-方 | 0.864 | [0.329, 2.271] | 0.766 |
| pack:b-长 | 1.183 | [0.469, 2.985] | 0.722 |
| pack:c-长 | 0.826 | [0.329, 2.070] | 0.683 |
| order=成分先 | 1.063 | [0.764, 1.478] | 0.719 |
| emph=突出 | 0.998 | [0.641, 1.555] | 0.993 |
| copy=无说明 | 1.023 | [0.662, 1.583] | 0.917 |

**含义正确**（1 = 能正确区分两种糖声明）：

| 项 | OR | 95% 区间 | p |
|---|---|---|---|
| pack:b-方 | 1.259 | [0.676, 2.342] | 0.468 |
| pack:b-长 | 1.081 | [0.563, 2.075] | 0.815 |
| pack:c-长 | 1.065 | [0.652, 1.740] | 0.801 |
| order=成分先 | 2.181 | [1.337, 3.557] | 0.002 |
| emph=突出 | 1.133 | [0.691, 1.858] | 0.622 |
| copy=无说明 | 1.523 | [0.797, 2.909] | 0.203 |

**高确信错误**（含义错且确信度 4）：

| 项 | OR | 95% 区间 | p |
|---|---|---|---|
| pack:b-方 | 0.389 | [0.124, 1.222] | 0.106 |
| pack:b-长 | 0.611 | [0.202, 1.846] | 0.382 |
| pack:c-长 | 0.689 | [0.244, 1.950] | 0.483 |
| order=成分先 | 0.259 | [0.126, 0.534] | 0.000 |
| emph=突出 | 0.546 | [0.199, 1.494] | 0.238 |
| copy=无说明 | 0.475 | [0.172, 1.311] | 0.151 |

- 读者组与属性的交互（含义）：LR=1.210, df=4, p=0.877。
- 读者组与属性的交互（高确信错误）：LR=2.341, df=4, p=0.673。
- 位置敏感性：块内左右顺序固定，位置项与块共线。加入位置项后 `order` 系数由 0.061 变为 -0.647（位置项 OR=1.765），说明**选择模型的属性系数不稳定**；位置效应无法与图稿分开，不应单独解释，也不应据此预测新组合。

**哪些属性改善理解、哪些只是吸引注意：**
- `order=成分先` 是唯一稳健改善含义的版式属性，同时显著降低高确信错误。它是“更好懂”，不只是更显眼。
- `emph=突出`、`copy=无说明`、`pack` 在含义与选择上都没有可分辨的效应；它们在这批资料里**没有被证据支持为改善理解**。
- 文案与格数别名意味着“删掉说明”的坏效果无法与“版面更小”分开；把无说明版式当成已被证明更易懂是不成立的。

## 4. 留出检查：哪些能迁移到新图稿

**留一对选择检查**（每次完全去掉一对再预测该对）：

| 留出块 | n | logloss | 均匀基线 | 预测左−右 | 观察左−右 | 首选命中 | 多数基线 |
|---|---|---|---|---|---|---|---|
| b1 | 63 | 0.983 | 1.099 | -0.245 | 0.051 | 0.508 | 0.492 |
| b2 | 60 | 1.030 | 1.099 | -0.230 | 0.094 | 0.517 | 0.483 |
| b3 | 60 | 1.113 | 1.099 | 0.107 | 0.000 | 0.583 | 0.417 |
| b4 | 60 | 1.063 | 1.099 | 0.531 | 0.036 | 0.550 | 0.483 |
| b5 | 60 | 0.937 | 1.099 | -0.137 | 0.214 | 0.433 | 0.567 |
| b6 | 60 | 0.977 | 1.099 | -0.239 | 0.091 | 0.500 | 0.500 |

**留一图稿含义检查**：

| 留出 | 包 | 含义预测 | 含义观察 | 高确信预测 | 高确信观察 | 包在训练集中 |
|---|---|---|---|---|---|---|
| d1 | a-圆 | 0.740 | 0.750 | 0.039 | 0.078 | True |
| d2 | a-圆 | 0.661 | 0.602 | 0.103 | 0.114 | True |
| d3 | a-圆 | 0.619 | 0.703 | 0.093 | 0.078 | True |
| d4 | b-方 | 0.765 | 0.781 | 0.070 | 0.000 | True |
| d5 | b-方 | 0.641 | 0.633 | 0.050 | 0.108 | True |
| d6 | b-长 | 0.601 | 0.594 | 0.127 | 0.141 | False |
| d7 | c-长 | 0.734 | 0.683 | 0.085 | 0.067 | True |
| d8 | c-长 | 0.729 | 0.782 | 0.044 | 0.032 | True |

**留一包检查**：
- a-圆：可估计=False；no training artwork in this pack: prediction is extrapolation and should be refused
- b-方：可估计=False；no training artwork in this pack: prediction is extrapolation and should be refused
- b-长：可估计=False；no training artwork in this pack: prediction is extrapolation and should be refused
- c-长：可估计=False；no training artwork in this pack: prediction is extrapolation and should be refused

**按人 5 折检查**：

| 结果 | logloss | 基线 | Brier | 基线 |
|---|---|---|---|---|
| meaning | 0.622 | 0.629 | 0.215 | 0.219 |
| hce | 0.285 | 0.291 | 0.077 | 0.077 |

**读法：**
- 含义模型在留一图稿上接近观察值（除个别小样本），说明**成分先/声明先这一条属性**可以外推到新组合；但当包完全不在训练集时（留一包），包固定效应无估计，预测应拒绝而不是外推。
- 选择模型留一对的 logloss 只略好于均匀，预测的左右差与观察方向常不一致：**选择结果只描述已展示过的组合**，不足以预测未展示的新组合；新对子需要重新测试。
- 高确信错误在留一图稿上量级可复现（63 个事件，岭罚稳定了原本会发散的格子），但它的事件太少、区间很宽，只适合作为**监测指标**，不足以支撑对单个新图稿的硬性预测。

## 5. 按政策评估每个图稿

政策：商品误解上限、读者组最低理解门槛、高确信错误上限。同组同时适用时取更严的一侧（上限取小、门槛取大）。

| 图稿 | 商品 | 读者组 | n | 理解 [95%CI] | 误解 | 高确信错误 | 通过 | 未过项 |
|---|---|---|---|---|---|---|---|---|
| d1 | a | 老读者 | 32 | 0.781 [0.625, 0.914] | 0.219 | 0.031 [0.000, 0.107] | 否 | misunderstanding |
| d2 | a | 老读者 | 46 | 0.565 [0.417, 0.711] | 0.435 | 0.065 [0.000, 0.146] | 否 | misunderstanding, understanding |
| d3 | a | 老读者 | 16 | 0.812 [0.600, 1.000] | 0.188 | 0.000 [0.000, 0.000] | 是 | — |
| d4 | b | 老读者 | 16 | 0.812 [0.600, 1.000] | 0.188 | 0.000 [0.000, 0.000] | 是 | — |
| d5 | b | 老读者 | 45 | 0.600 [0.469, 0.725] | 0.400 | 0.089 [0.020, 0.179] | 否 | misunderstanding, understanding |
| d6 | b | 老读者 | 48 | 0.625 [0.489, 0.756] | 0.375 | 0.167 [0.070, 0.276] | 否 | misunderstanding, understanding, high_confidence_error |
| d7 | c | 老读者 | 15 | 0.667 [0.412, 0.900] | 0.333 | 0.067 [0.000, 0.231] | 否 | misunderstanding, understanding |
| d8 | c | 老读者 | 31 | 0.710 [0.538, 0.862] | 0.290 | 0.065 [0.000, 0.162] | 否 | misunderstanding, understanding |
| d1 | a | 普通读者 | 32 | 0.719 [0.556, 0.867] | 0.281 | 0.125 [0.029, 0.256] | 否 | misunderstanding, understanding, high_confidence_error |
| d2 | a | 普通读者 | 77 | 0.623 [0.494, 0.740] | 0.377 | 0.143 [0.067, 0.227] | 否 | misunderstanding, understanding, high_confidence_error |
| d3 | a | 普通读者 | 48 | 0.667 [0.524, 0.794] | 0.333 | 0.104 [0.024, 0.200] | 否 | misunderstanding, understanding, high_confidence_error |
| d4 | b | 普通读者 | 48 | 0.771 [0.644, 0.882] | 0.229 | 0.000 [0.000, 0.000] | 是 | — |
| d5 | b | 普通读者 | 75 | 0.653 [0.541, 0.761] | 0.347 | 0.120 [0.053, 0.203] | 否 | misunderstanding, understanding |
| d6 | b | 普通读者 | 80 | 0.575 [0.473, 0.671] | 0.425 | 0.125 [0.060, 0.200] | 否 | misunderstanding, understanding, high_confidence_error |
| d7 | c | 普通读者 | 45 | 0.689 [0.547, 0.814] | 0.311 | 0.067 [0.000, 0.150] | 否 | misunderstanding, understanding |
| d8 | c | 普通读者 | 93 | 0.806 [0.717, 0.889] | 0.194 | 0.022 [0.000, 0.055] | 是 | — |
| d1 | a | ALL | 64 | 0.750 [0.639, 0.853] | 0.250 | 0.078 [0.016, 0.149] | 否 | misunderstanding |
| d2 | a | ALL | 123 | 0.602 [0.504, 0.695] | 0.398 | 0.114 [0.061, 0.174] | 否 | misunderstanding, understanding, high_confidence_error |
| d3 | a | ALL | 64 | 0.703 [0.585, 0.809] | 0.297 | 0.078 [0.016, 0.147] | 否 | misunderstanding, understanding |
| d4 | b | ALL | 64 | 0.781 [0.677, 0.877] | 0.219 | 0.000 [0.000, 0.000] | 是 | — |
| d5 | b | ALL | 120 | 0.633 [0.549, 0.714] | 0.367 | 0.108 [0.057, 0.167] | 否 | misunderstanding, understanding |
| d6 | b | ALL | 128 | 0.594 [0.512, 0.674] | 0.406 | 0.141 [0.084, 0.202] | 否 | misunderstanding, understanding, high_confidence_error |
| d7 | c | ALL | 60 | 0.683 [0.559, 0.800] | 0.317 | 0.067 [0.016, 0.138] | 否 | misunderstanding, understanding |
| d8 | c | ALL | 124 | 0.782 [0.702, 0.854] | 0.218 | 0.032 [0.008, 0.067] | 是 | — |

按商品的最差情况汇总：

| 商品 | 读者组 | 最差误解 | 最差高确信 | 最低理解 | 全部通过 |
|---|---|---|---|---|---|
| a | 老读者 | 0.435 | 0.065 | 0.565 | 否 |
| a | 普通读者 | 0.377 | 0.143 | 0.623 | 否 |
| b | 老读者 | 0.400 | 0.167 | 0.600 | 否 |
| b | 普通读者 | 0.425 | 0.125 | 0.575 | 否 |
| c | 老读者 | 0.333 | 0.067 | 0.667 | 否 |
| c | 普通读者 | 0.311 | 0.067 | 0.689 | 否 |

**总体胜出但按商品超限的例子：** 以 t1 的两个图稿为例，a 的 d1 误解 0.250、b 的 d4 为 0.219；合并后约 0.234。若拿合并率去对 b 的较宽上限（0.24）就“通过”，但对 a 的 0.21 已经超限——这正是**一款商品的优势抵掉另一款超限**的掩盖。放行必须按商品分别判断。

## 6. 共用模板与制版位

| 模板 | 状态 | 商品 | 版位 | 文案 | 格数 | 内部一致 | 阻塞点 |
|---|---|---|---|---|---|---|---|
| t1 | 候选 | a/b | P01 | 未加蔗糖说明 | 5 | 是 | — |
| t2 | 候选 | a/b | P01 | 不同说明 | 5 | 否 | template declares differing copy text; one plate cannot hold two texts; designs disagree on layout signature (copy/order/emphasis/cells) |
| t3 | 候选 | b/c | P02 | 未加蔗糖说明 | 5 | 否 | designs disagree on layout signature (copy/order/emphasis/cells) |
| t4 | 已签 | a | P02 | 保留的既有文字 | 6 | 是 | — |
| t5 | 候选 | c | P03 | 无附加说明 | 4 | 是 | — |

| 模板 | 状态 | 商品全部通过 | 逐商品结论 | 建议 | 版位冲突 |
|---|---|---|---|---|---|
| t1 | 候选 | 否 | a:未过(老读者,普通读者,ALL)；b:通过 | split | 是 |
| t2 | 候选 | 否 | a:未过(老读者,普通读者,ALL)；b:未过(老读者,普通读者,ALL) | rebuild_and_split | 是 |
| t3 | 候选 | 否 | b:未过(老读者,普通读者,ALL)；c:未过(老读者) | rebuild_and_split | 否 |
| t4 | 已签 | 否 | a:未过(老读者,普通读者,ALL) | signed_review | 否 |
| t5 | 候选 | 否 | c:未过(老读者,普通读者,ALL) | retest | 否 |

建议口径：`keep` 保留；`split` 一版内商品表现不一致，需人工拆版；`rebuild_and_split` 交付的内部文字不一致，不能作为一块版成立，需重建并拆版；`retest` 所有商品都未通过，需补测试；`signed_keep`/`signed_review` 针对已签版本，分别表示按原依据保留/需重审。

- 已签版位（为尚未切换商品保留）：P02。
- 候选占用的版位：P01, P02, P03。
- 空白版位：无；可承接新文字签名的版位：无。
- 拆版需要新制版位：是。
  - `P01`：candidates carry incompatible text sets and cannot share this plate（incompatible_candidates）。
  - `P02`：signed plate is reserved for its product; candidates must not reuse it（signed_reserved）。
- 不能用“把同一版位重复分给两套不兼容文字”来避免拆版；拆版应占用额外制版位。

## 7. 图稿更正后的证据复核

- 事件 `e1`：d5 的 `emphasis` 由 `突出` 更正为 `普通`，知悉日 2026-10-06。
  - 更正前试验 120 条、更正后 0 条；contested: trials ran before the correction and used the old value。
  - 引用该图稿的模板：t2；已签：无。
  - `b3`（d4 vs d5）变更属性 ['order', 'emphasis'] → ['order']。
  - `b4`（d5 vs d6）变更属性 ['emphasis', 'shape'] → ['shape']。

| 模板 | 状态 | 触及更正 | 内部一致 | 变更属性 | 被成对孤立支持 | 证据可用 | 原因 |
|---|---|---|---|---|---|---|---|
| t1 | 候选 | — | 是 | — | — | 否 | no attribute contrast among its designs |
| t2 | 候选 | d5 | 否 | emphasis | — | 否 | references corrected artwork d5; designs cannot share one plate text; delivered pairs never isolate emphasis |
| t3 | 候选 | — | 否 | emphasis, order | order | 否 | designs cannot share one plate text |
| t4 | 已签 | — | 是 | — | — | 否 | no attribute contrast among its designs |
| t5 | 候选 | — | 是 | — | — | 否 | no attribute contrast among its designs |

**已上版对象的重审范围与保留依据：**
- `t4`：图稿未触及更正，版面文字与观察一致；保留依据：按原试验证据与签批记录保留；无新证据前不扩用到其他商品。

## 8. 下次送审的判定口径

编辑用同一口径可把每个商品 x 读者组归为五类：`plate_short`（版位格数不够）、`not_estimable`（资料无法估计）、`over_cap`（点估计已超上限）、`possibly_over_cap`（点估计未超但区间触及上限）、`passes`（通过）。

### t1（['a', 'b']）
- a / 老读者：`over_cap` — estimated misunderstanding 0.253 exceeds cap 0.210
- a / 普通读者：`over_cap` — estimated misunderstanding 0.253 exceeds cap 0.210
- b / 老读者：`passes` — estimated and clears every applicable threshold
- b / 普通读者：`passes` — estimated and clears every applicable threshold

### t2（['a', 'b']）
- a / 老读者：`over_cap` — estimated misunderstanding 0.395 exceeds cap 0.210
- a / 普通读者：`over_cap` — estimated misunderstanding 0.395 exceeds cap 0.210
- b / 老读者：`over_cap` — estimated misunderstanding 0.370 exceeds cap 0.240
- b / 普通读者：`over_cap` — estimated misunderstanding 0.370 exceeds cap 0.240

### t3（['b', 'c']）
- b / 老读者：`over_cap` — estimated misunderstanding 0.406 exceeds cap 0.240
- b / 普通读者：`over_cap` — estimated misunderstanding 0.406 exceeds cap 0.240
- c / 老读者：`possibly_over_cap` — misunderstanding upper bound 0.232 exceeds cap 0.220; point estimate does not
- c / 普通读者：`possibly_over_cap` — misunderstanding upper bound 0.232 exceeds cap 0.220; point estimate does not

### t4（['a']）
- a / 老读者：`over_cap` — estimated misunderstanding 0.253 exceeds cap 0.210
- a / 普通读者：`over_cap` — estimated misunderstanding 0.253 exceeds cap 0.210

### t5（['c']）
- c / 老读者：`over_cap` — estimated misunderstanding 0.313 exceeds cap 0.220
- c / 普通读者：`over_cap` — estimated misunderstanding 0.313 exceeds cap 0.220

**共用属性变化的影响范围：**
- `t1`：变更一个共用属性会同时影响 a, b；可承接新签名的版位：无。
- `t2`：变更一个共用属性会同时影响 a, b；可承接新签名的版位：无。
- `t3`：变更一个共用属性会同时影响 b, c；可承接新签名的版位：无。
- `t4`：变更一个共用属性会同时影响 a；可承接新签名的版位：无。
- `t5`：变更一个共用属性会同时影响 c；可承接新签名的版位：无。

## 9. 给设计与编辑的结论

1. **保留并优先使用成分先在前的版式**：它是唯一同时改善理解并降低高确信错误的属性。
2. **“突出”和“删说明”不要当作改善理解的手段。** 突出没有可分辨的理解收益；删说明与少占格完全别名，现有资料无法证明它更好懂，也不能归因于“说明本身”。
3. **共用模板 t1 不能整版放行。** 它在商品 b 上通过、在商品 a 上误解超限，属于“一商品优势抵消另一商品超限”，应**交编辑人工拆版**，并占用额外制版位。
4. **t2/t3 不能作为一块版成立**：t2 声明两块文字不同，t3 的两个图稿在顺序与强调上不一致，同一版位无法容纳两套固定文字；需**重建并拆版**（或统一文案后重测），不能靠重复分配版位规避。
5. **t3 还占用已签版位 P02 且与 t4 不兼容**，必须另取版位；不能重复分配 P02。
6. **选择结果不能外推到未展示的新组合**：留一对预测接近均匀，任何新对子都需要新测试。
7. **更正后的证据**：d5 的强调属性更正在所有试验之后，t2 引用 d5，其强调对比不能被现有试验支持；b3 因此由“顺序+强调”两属性对比退化为**只识别顺序**（更正后），这也是“成分先”效应能够被单独立住的关键。

## 附：复现

```sh
python3 inspect_inputs.py data
python3 -m unittest discover -s tests -v
python3 -m analysis.report data --md REPORT.md --json analysis.json
```
