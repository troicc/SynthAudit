# SynthAudit 小白级原理与操作手册

> 适用范围：SynthAudit v1.x direct-use 工作流  
> 重要边界：SynthAudit 检查反应表示、图编辑、语料新颖性和证据支持度；它不证明实验一定成功，也不预测真实产率、安全性或放大结果。

---

## 1. 先用一句话理解项目

你可以把 SynthAudit 想成“化学反应方案的编译器、静态检查器和审计报告生成器”。

程序员写代码以后，会经过：

```text
源代码 → 统一语法树 → 编译 → 静态检查 → 测试和报告
```

SynthAudit 对化学反应做的是：

```text
外部反应表示
→ 统一 ReactionIR
→ 按图编辑执行
→ 检查反应中心、前体补全、立体化学和结构
→ 可选检索先例与新颖性
→ 输出 JSON、HTML 和图形界面报告
```

它不是替你设计路线的 SynthEx，也不是从产品预测前体的 ReactSeq 模型。它负责接住这些系统的输出，回答下面的问题：

1. 这段反应表示能不能被明确解释？
2. 它声称断开的键、添加的片段和改变的立体化学，是否真的得到所声明的前体？
3. 哪一步是确定性错误，哪一步只是证据不足？
4. 该转化对某个指定数据库来说有多陌生？
5. 哪些步骤应该交给化学家重点复核？

---

# 2. 先认识项目中的几个化学名词

## 2.1 分子在程序里是一张图

一个有机分子可以看成：

```text
原子 = 图的节点
化学键 = 图的边
```

例如乙醇 `CCO` 可以抽象成：

```text
C — C — O
```

所谓“反应”，在计算机中常常被表达为对这张图进行修改：

- 删除一条键；
- 新增一条键；
- 把单键改成双键；
- 改变原子电荷；
- 添加一个外部片段；
- 改变手性。

SynthAudit 的执行器就是在做这种明确的图编辑。

## 2.2 什么是 SMILES

SMILES 是把分子图写成字符串的一种方法。例如：

```text
乙醇：CCO
苯：c1ccccc1
乙酸：CC(=O)O
```

同一个分子可能有不止一种合法 SMILES，因此不能简单用原始字符串是否完全相同来判断两个分子是否相同。

## 2.3 什么是 reaction SMILES

反应 SMILES 常写成：

```text
reactants>reagents>product
```

没有单独试剂字段时，常写成：

```text
reactants>>product
```

左侧有多个分子时，用点分隔：

```text
A.B>>C
```

点表示两个分离的分子，不表示化学键。

## 2.4 什么是 atom map

为了知道产品里的某个碳来自反应物里的哪个碳，可以给原子编号：

```text
[CH3:1][OH:2]
```

`:1`、`:2` 就是 atom-map number。

它们不是：

- SMILES 字符串中的第几个字符；
- RDKit 分子对象里的临时 atom index；
- ReactSeq 的 traversal position。

它们是跨反应两侧追踪原子身份的稳定标签。

SynthAudit 的确定性核心默认要求输入已经 atom-mapped。若输入没有 map，程序不会偷偷猜测。只有显式加上 `--map-if-needed`，它才会调用可选 RXNMapper，并把映射来源和置信信息保存下来。

## 2.5 Product、synthon 和 precursor 的区别

### Product

要被逆合成分析的目标分子。

### Synthon

对 product 进行核心断键或键级修改后得到的概念片段。它不一定是能直接拿进实验室的稳定试剂。

### Precursor

在 synthon 上补齐 leaving group、氢、电荷或其他外部片段以后得到的完整前体分子。

ReactSeq 的核心分解正是：

```text
product → synthons → precursors
```

SynthAudit 也按照这个顺序执行，所以能区分“反应中心错了”和“反应中心对了但前体补错了”。

---

# 3. 为什么需要统一的 ReactionIR

不同系统对同一个反应使用不同语言：

- mapped reaction SMILES 通过反应两侧的图差异隐式表达变化；
- ReactSeq 把 product→synthon 的编辑写在 header，把 synthon→reactant 的 leaving-group completion 写在 tail；
- SynthEx 用类似程序指令的 ReactionJSON 表达断键、改键级、加片段等操作；
- Synthelite 输出搜索树和模板规划结果。

若每一种格式都单独写一套审核逻辑，项目会变成很多互不一致的分支。因此 SynthAudit 先把它们转成统一的：

```text
ReactionIRV1
```

ReactionIR 不是 ReactSeq，也不是 SynthEx 的官方 ReactionJSON。它是 SynthAudit 自己稳定、版本化的内部语言。

核心字段可以理解为：

```text
product                  目标分子
expected_precursors      上游声明或数据记录中的前体
core_edits               核心键变化
attachment_edits         外部片段或 leaving group 补全
atom_state_edits         电荷、氢、同位素、芳香性等变化
stereo_edits             R/S、CW/CCW、E/Z 等变化
conditions               可选反应条件
provenance               数据和转换来自哪里
metadata                 其他不参与核心语义的信息
```

## 3.1 Core edits

改变 product 中已有原子之间的键：

- `break_bond`：断开一条键；
- `add_bond`：在逆合成方向新增一条键；
- `change_bond_order`：单键、双键或三键发生变化。

## 3.2 Attachment edits

处理 product 中没有、但 precursor 中需要出现的外部片段：

- `attach_fragment`；
- `detach_fragment`；
- null completion；
- charge-only completion。

一个典型情况是：产品断键以后得到两个 synthons，但真正的反应物还需要给其中一个片段补上卤素、硼酸基、金属或其他 leaving group。

## 3.3 Atom-state edits

处理原子本身的属性：

- formal charge；
- isotope；
- aromaticity；
- atomic number；
- explicit hydrogen。

## 3.4 Stereo edits

处理空间构型：

- 设置 R/S 或 CW/CCW；
- 翻转手性中心；
- 清除手性定义；
- 设置或清除 E/Z。

## 3.5 ReactionIR 的真正价值

新的反应系统接入时，只需要写一个 adapter：

```text
新格式 → ReactionIR
```

后面的执行器、审核器、新颖性、路线审核、CLI 和报告全部复用。

---

# 4. 输入适配器在做什么

代码主要位于：

```text
src/synthaudit/adapters/
```

## 4.1 Mapped reaction SMILES adapter

它读取：

```text
reactants>reagents>product
```

然后：

1. 解析 product；
2. 检查 product 原子是否都有正 atom map；
3. 区分 fully mapped participating reactants 与 unmapped reagents；
4. 找出 product 和 precursor 共有的 atom maps；
5. 比较共有原子之间的键；
6. 找出 precursor 中额外出现的外部片段；
7. 比较电荷、显式氢和立体化学；
8. 生成 ReactionIR。

它不会把 unmapped reagent 偷偷当作 precursor，也不会在一半 mapped、一半 unmapped 的片段上猜测。

## 4.2 ReactSeq adapter

ReactSeq 的原子引用与具体 product SMILES 的遍历顺序有关。SynthAudit 必须经过：

```text
ReactSeq traversal position
→ RDKit atom
→ stable atom-map number
```

所以：

```text
ReactSeq index ≠ RDKit atom index ≠ atom map
```

当前适配器是保守的 `source-inspected safe subset`，而不是完整官方兼容声明。遇到不能唯一解释的对称位置时，它返回 indeterminate 或拒绝，而不是任意选一个位置。

## 4.3 SynthEx adapter

截至项目固定的上游版本，SynthEx 没有公开完整官方 ReactionJSON/RouteJSON schema。因此项目只提供显式命名的 paper-draft adapter。

这意味着：

- 可用于论文中已经明确描述的操作；
- 不能声称完全兼容未来官方实现；
- 官方 adapter 在规范缺失时 fail closed。

## 4.4 Synthelite adapter

Synthelite 当前导出的是实现相关的嵌套 reaction tree，不是稳定跨项目标准。SynthAudit 只支持已检查过的固定结构，并要求有明确 mapped reaction SMILES。

---

# 5. 执行器到底在做什么

代码主要位于：

```text
src/synthaudit/graph/
```

完整执行顺序：

```text
mapped product
→ CoreGraphExecutor
→ synthons
→ AttachmentCompletionExecutor
→ completed precursors
→ StereoExecutor
→ final mapped precursor set
```

## 5.1 CoreGraphExecutor

它先复制 product，再逐条执行核心编辑。

例如：

```text
break_bond(map_a=11, map_b=13)
```

执行时会：

1. 找到 map 11 和 map 13；
2. 检查二者不是同一原子；
3. 检查二者之间真的存在键；
4. 若指定 expected bond order，再核对键级；
5. 删除键；
6. 记录 graph diff。

## 5.2 AttachmentCompletionExecutor

它把 leaving group 或外部 fragment 接到 synthons 上。

会检查：

- fragment SMILES 能否解析；
- fragment maps 是否与已有 map 冲突；
- product attachment atom 是否存在；
- fragment attachment atom 是否存在；
- bond order 是否有效；
- 补全后的价态和 sanitation 是否有效。

## 5.3 StereoExecutor

最后处理手性和双键立体化学。之所以放在最后，是因为前面的加键、断键可能改变一个原子的邻居和 CIP 排序。

## 5.4 什么叫事务式执行

事务式意味着：

```text
全部成功 → 返回最终结果
任一步失败 → 不把半完成结构冒充成功结果
```

失败时仍然可以看到：

- 失败阶段；
- operation index；
- affected atom maps；
- RDKit error；
- diagnostic graph。

但是 diagnostic graph 不会被标记为 structurally valid。

## 5.5 Strict 与 diagnostic

### Strict

只要最终 sanitation 失败，本次执行就失败。

### Diagnostic

保留失败图供排查，但不会把它升级成成功结果。

---

# 6. 为什么执行成功仍不等于反应可行

执行器只回答：

> 这些图编辑能否得到一个 RDKit 可以表示的分子图？

它不回答：

- 反应动力学是否允许；
- 有没有副反应；
- 是否具有化学选择性；
- 是否具有区域或立体选择性；
- 中间体是否稳定；
- 是否容易分离；
- 产率多少；
- 是否安全；
- 能否放大。

因此执行器之后还有审核器，而且最终仍需要专家和实验。

---

# 7. 四类单步审核器

代码主要位于：

```text
src/synthaudit/audit/
```

## 7.1 StructuralAudit

检查：

- atom-map 唯一性；
- dangling map reference；
- valence；
- formal charge；
- aromaticity 和 Kekulé 一致性；
- connectivity；
- 空片段或可疑单原子片段；
- atom conservation；
- no-op；
- unexplained graph changes；
- 异常复杂的编辑。

## 7.2 ReactionCentreAudit

检查：

- 声明的断键、加键、改键级是否与实际 graph diff 一致；
- ring opening/closure 是否与操作一致；
- 是否存在对称位置歧义；
- expected precursor 是否支持所声明的 reaction centre。

## 7.3 SynthonCompletionAudit

检查：

- fragment 是否可解析；
- attachment point 是否存在；
- 多连接 leaving group 是否一致；
- 外部原子是否都得到解释；
- charge 和 valence 是否合理；
- expected precursor 是否被重建。

## 7.4 StereoAudit

检查：

- 被设置或翻转的手性中心是否存在；
- CIP 意图是否实现；
- E/Z 的 reference neighbours 是否明确；
- stereo 是否被静默删除；
- 新生成 stereocentre 是否遗漏；
- 对称、pseudo-asymmetric 或复杂环体系是否应该标为 indeterminate。

## 7.5 六种状态怎样读

| 状态 | 含义 |
|---|---|
| `pass` | 在该检查明确定义下通过 |
| `warning` | 有风险，需要复核，但不是确定性阻断 |
| `fail` | 发现明确冲突 |
| `unavailable` | 缺少输入、语料或 provider |
| `unsupported` | 当前软件没有实现该语义 |
| `indeterminate` | 因对称性、立体化学或证据歧义无法可靠判断 |

不要把 `unavailable` 当作 `pass`，也不要把 `indeterminate` 自动当作 `fail`。

---

# 8. 路线审核在做什么

`RouteIRV1` 把多步路线写成显式 dependency graph。每一步都包含自己的 ReactionIR。

主要字段：

```text
step_id
reaction
depends_on
consumes
produces
strategy_text
key_step
metadata
```

路线审核检查：

- step ID 是否唯一；
- dependency 是否存在；
- dependency graph 是否有环；
- 前一步是否在后一步之前；
- intermediate 是否连续；
- target 是否由终端步骤产生；
- 同一中间体的 atom maps 是否一致；
- 是否存在重复或冗余步骤；
- protection/deprotection timing；
- fragile intermediate 是否遇到不兼容条件；
- 哪一步是高新颖或高不确定 bottleneck。

项目不会把每一步分数简单相乘并称为“路线成功率”，因为各步骤并不独立，而且单步模型分数也不是实验概率。

---

# 9. 新颖性和证据支持度为什么必须分开

某反应在专利数据库中少见，可能有两种完全不同的原因：

1. 它确实不合理；
2. 它是天然产物全合成中合理但低频的骨架构建。

所以：

```text
novelty ≠ implausibility
```

SynthAudit 分别查看：

- product structure similarity；
- precursor structure similarity；
- reaction-difference similarity；
- reaction-centre similarity；
- leaving-group similarity；
- stereo similarity；
- 可选 ReactSeq MEO embedding；
- 可选 reaction taxonomy recognition。

例如：

```text
product similarity 低
transformation similarity 高
```

表示“底物骨架很新，但执行的是常见转化”。这不应该被简单判成高风险。

## 9.1 先例不是实验验证

PrecedentRetriever 找到相似反应，只说明存在某种相似证据。它不能证明当前底物在当前条件下一定成功。

## 9.2 当前索引的适用范围

当前 ReferenceIndex 适合小型和中小型本地语料。超大规模语料需要预计算指纹和向量化索引；在没有完成规模 benchmark 前，不应把当前实现宣传成百万反应级搜索服务。

---

# 10. 证据模型和训练

日常结构审核不需要训练模型。

项目中的模型层用于研究下列量：

```text
reaction_centre_supported
completion_supported_given_reaction_centre
stereo_specification_supported
route_context_supported
```

支持：

- Logistic Regression；
- Histogram Gradient Boosting；
- Platt calibration；
- Isotonic calibration；
- bootstrap uncertainty；
- OOD diagnostics；
- abstention。

即使经过校准，输出也只能称为 evidence-support score，不能称为实验成功率。

## 10.1 哪些功能不需要训练

- schema validation；
- atom-map 检查；
- graph-edit execution；
- valence、aromaticity 和 connectivity；
- graph diff；
- expected precursor reconstruction；
- representation semantic comparison；
- route dependency；
- HTML/JSON 报告。

## 10.2 哪些功能需要模型或外部数据

- 可泛化的 evidence ranking；
- ReactSeq MEO embedding；
- forward-reaction support；
- prompt robustness；
- 校准后的大规模候选排序；
- 数据驱动的 route-context support。

---

# 11. 安装

## 11.1 推荐：源码安装

先安装 Git 和 uv，然后运行：

```bash
git clone https://github.com/troicc/SynthAudit.git
cd SynthAudit
uv sync --frozen --all-extras --dev
uv run synthaudit-easy doctor
```

`doctor` 会报告：

- Python 版本；
- SynthAudit 版本；
- RDKit、Pydantic、Typer、scikit-learn；
- Streamlit 是否存在；
- RXNMapper 是否存在；
- ReactionClassifier 是否存在。

项目当前要求 Python 3.11。

## 11.2 Docker

```bash
docker compose build
docker compose run --rm synthaudit-ui synthaudit-easy doctor
docker compose up
```

浏览器访问：

```text
http://localhost:8501
```

Docker 默认只包含核心与 UI，不自动安装大型映射或分类模型。

---

# 12. 最简单的单反应审核

运行：

```bash
uv run synthaudit-easy audit \
  --input examples/mapped-reaction.smi \
  --output-dir synthaudit-output
```

输出：

```text
synthaudit-output/
├── mapped-reaction.smi
├── reaction-ir.json
├── audit.json
├── audit.html
└── summary.json
```

## 12.1 每个文件是什么

### mapped-reaction.smi

程序实际使用的 mapped reaction SMILES。若发生显式 mapping，这里保存 mapping 后版本。

### reaction-ir.json

外部输入归一化后的 ReactionIR。排查 adapter 时首先看它。

### audit.json

完整机器可读审核结果，适合后续脚本和批处理。

### audit.html

无需服务器即可打开的可视化报告。

### summary.json

最适合日常先看的摘要：

- `structurally_valid`；
- `blocking`；
- `failure_and_review_checks`；
- `mapping_used`；
- 输出文件位置。

## 12.2 命令退出码

| 退出码 | 含义 |
|---:|---|
| 0 | 审核完成且没有 blocking failure |
| 2 | 输入、依赖或批处理基础错误 |
| 3 | 审核已完成，但发现 blocking representation issue |

退出码 3 不表示实验一定失败。

---

# 13. 输入没有 atom map

安装可选 RXNMapper：

```bash
uv pip install rxnmapper
```

显式运行：

```bash
uv run synthaudit-easy audit \
  --reaction 'CCO.CC(=O)O>>CCOC(C)=O' \
  --map-if-needed \
  --output-dir synthaudit-output
```

项目额外保存：

```text
mapping.json
```

其中包括：

- 原始反应；
- mapped reaction；
- provider；
- provider version；
- raw confidence；
- 科学边界说明。

Mapping 本身可能出错，所以它始终被当作可审计预处理，不是隐藏步骤。

---

# 14. 可选反应分类

安装：

```bash
uv pip install reactionclassifier
```

运行：

```bash
uv run synthaudit-easy audit \
  --input examples/mapped-reaction.smi \
  --with-classifier \
  --output-dir synthaudit-output
```

输出：

```text
classification.json
```

请区分：

- `confirmed_code`：某个具体模板确实复现了声明产品；
- `neural_code`：神经 gate 的候选分类；
- `neural_raw_confidence`：未经 SynthAudit 校准的原始分数。

模板确认也不等于实验可行，只说明该转化与模板定义一致。

---

# 15. 批量审核

CSV 示例：

```csv
reaction_id,reaction_smiles
rxn-1,"mapped reaction here"
rxn-2,"another mapped reaction"
```

运行：

```bash
uv run synthaudit-easy batch \
  --input examples/reactions.csv \
  --output-dir synthaudit-batch-output \
  --reports
```

也支持 TSV 和 JSONL。默认字段名：

```text
reaction_id
reaction_smiles
```

自定义字段：

```bash
uv run synthaudit-easy batch \
  --input my-data.csv \
  --reaction-column mapped_rxn \
  --id-column id \
  --output-dir result
```

输出结构：

```text
synthaudit-batch-output/
├── results.jsonl
├── summary.json
└── records/
    └── rxn-1/
        ├── mapped-reaction.smi
        ├── reaction-ir.json
        ├── audit.json
        └── audit.html
```

批量模式会捕获单条记录错误并继续处理其他记录；最后若存在输入错误，退出码为 2。

---

# 16. 原有高级命令

```bash
uv run synthaudit --help
```

主要命令：

- `normalize-reaction`：外部格式转 ReactionIR；
- `parse-reactseq`：解析 ReactSeq；
- `execute-reaction`：只执行图编辑；
- `audit-reaction`：完整单步审核；
- `audit-route`：多步路线审核；
- `compare-representations`：比较不同格式的化学语义；
- `data prepare`：创建本地先例索引；
- `novelty score`：计算多视角新颖性；
- `precedent search`：检索先例；
- `train`、`evaluate`：训练和评估研究模型；
- `ui`：启动图形工作区。

直接使用命令：

```bash
uv run synthaudit-easy --help
```

`easy` 命令并没有新写一套化学逻辑，它只是把现有 adapter、ReactionIR、auditor 和 report 串起来，减少手工准备步骤。

---

# 17. 怎样阅读 HTML 报告

建议按顺序看：

1. **Input/source**：输入及来源；
2. **Normalization**：输入被怎样转成 ReactionIR；
3. **Product→synthon**：核心断键和键级变化；
4. **Synthon→precursor**：外部片段和 leaving group；
5. **Stereo**：手性和 E/Z；
6. **Structural alerts**：确定性结构问题；
7. **Novelty**：相对于指定语料的陌生度；
8. **Precedents**：相似反应证据；
9. **Evidence**：可选模型支持度；
10. **Uncertainty**：缺失、分歧和 abstention；
11. **Limitations**：报告不能证明什么。

正确阅读顺序是：

```text
blocking deterministic error
→ warning / indeterminate
→ novelty and precedent
→ optional model evidence
```

不要一上来只盯着一个模型分数。

---

# 18. 如何排查常见错误

## 18.1 AtomMappingRequired

原因：输入没有完整、唯一的正 atom maps。

解决：

- 使用已 mapping 的数据；或
- 安装 RXNMapper 后显式加 `--map-if-needed`。

## 18.2 SanitationError

原因：RDKit 无法把编辑后的图解释成合法结构。

查看：

- failure stage；
- operation index；
- affected atom maps；
- diagnostic graph；
- valence/aromaticity 错误。

## 18.3 unavailable

不是失败。表示缺少 reference corpus、checkpoint 或 provider。配置资源后重跑。

## 18.4 unsupported

当前 adapter 或 executor 没有定义该语义。不要把它改成 pass；应新增明确规范和测试。

## 18.5 indeterminate

常见于：

- 对称原子；
- 复杂环手性；
- pseudo-asymmetric centre；
- 无法唯一确定的 E/Z neighbours。

正确动作是人工复核，而不是任意选择一个答案。

## 18.6 blocking=true

至少有一项表示级检查明确失败。打开 `summary.json` 中的 `failure_and_review_checks`，按 check ID 和 atom maps 定位。

---

# 19. 怎样验证安装没有坏

```bash
make quality
make test
make doctor
make easy-smoke
make reproduce-small
```

含义：

- `quality`：Ruff、格式和 mypy；
- `test`：离线单元、属性、回归和部分集成测试；
- `doctor`：环境自检；
- `easy-smoke`：直接使用入口真实跑一遍；
- `reproduce-small`：项目全部小型可复现链路。

---

# 20. 代码阅读顺序

不要从 200 多个文件中随机开始。建议：

## 第一步：领域模型

```text
README.md
docs/PROJECT_SPEC.md
src/synthaudit/schema/common.py
src/synthaudit/schema/edits.py
src/synthaudit/schema/reaction_ir.py
src/synthaudit/schema/route_ir.py
```

目标：能手写最小 ReactionIR，并解释四类 edits。

## 第二步：mapped reaction adapter

```text
src/synthaudit/application/workflows.py
src/synthaudit/adapters/mapped_reaction_smiles.py
```

目标：能说明 reaction SMILES 怎样变成 ReactionIR。

## 第三步：执行器

```text
src/synthaudit/graph/core_executor.py
src/synthaudit/graph/completion_executor.py
src/synthaudit/graph/stereo_executor.py
src/synthaudit/graph/executor.py
src/synthaudit/graph/diff.py
```

目标：能追踪一个 edit 的前置条件和失败位置。

## 第四步：审核器

```text
src/synthaudit/audit/structural.py
src/synthaudit/audit/reaction_centre.py
src/synthaudit/audit/completion.py
src/synthaudit/audit/stereo.py
src/synthaudit/audit/reaction.py
```

目标：能解释 execution success 与 audit pass 的区别。

## 第五步：新颖性和先例

```text
src/synthaudit/novelty/fingerprints.py
src/synthaudit/novelty/engine.py
src/synthaudit/precedent/index.py
src/synthaudit/precedent/retrieval.py
```

目标：能解释 structure similarity 与 transformation similarity 的不同。

## 第六步：模型

```text
src/synthaudit/models/evidence.py
src/synthaudit/models/extraction.py
src/synthaudit/models/training.py
src/synthaudit/models/evaluation.py
src/synthaudit/calibration/
```

目标：理解 train/calibration/test、parent grouping、missing flags 和 abstention。

## 第七步：路线

```text
src/synthaudit/schema/route_ir.py
src/synthaudit/audit/route.py
```

目标：能制造 dependency、continuity 和 protection timing 错误。

## 第八步：产品面

```text
src/synthaudit/easy.py
src/synthaudit/cli/app.py
src/synthaudit/application/
src/synthaudit/reports/
app/
```

目标：理解 UI/CLI 只负责输入输出，核心化学逻辑仍在包内。

---

# 21. 怎样亲手熟悉项目

## 练习 1：制造 map 错误

复制一个 mapped reaction，把两个原子改成相同 map，运行 audit，观察哪一阶段失败。

## 练习 2：制造错误断键

在 ReactionIR 中把 `map_b` 改成不存在的 map，观察 operation index 和 affected maps。

## 练习 3：制造错误键级

改变 `from_order`，让它与 product 实际键级不一致。

## 练习 4：制造 completion 错误

把 fragment connection 指向错误 atom map，区分 executor failure 与 completion audit failure。

## 练习 5：制造 stereo 错误

把一个非手性原子设成 R/S，观察 `fail`、`unsupported` 或 `indeterminate` 的区别。

## 练习 6：制造路线错误

交换两个有依赖关系的 step，或者让终端步骤不再产生 target，运行 `audit-route`。

---

# 22. 模型训练前必须知道的事

当前项目不需要训练即可直接用于 deterministic audit。

若要训练 evidence model，必须先明确标签语义。

错误做法：

```text
标签 = deterministic centre check 是否通过
输入特征 = centre check pass fraction
```

这会造成 target leakage，模型只是在复述生成标签的规则。

正确做法：

- deterministic consistency 直接由规则输出；
- learned evidence 使用独立信息；
- 标签来自独立人工审核、外部先例协议或严格定义的 benchmark；
- corpus novelty 不自动作为负面 plausibility 特征；
- 同一个 parent reaction 及其所有 counterfactual 必须进入同一 split；
- calibration set 与 test set 必须独立；
- test 不参与模型选择和阈值设定。

建议第一版只训练：

- Logistic Regression；
- Histogram Gradient Boosting。

先完成透明 baseline、校准、OOD 和错误分析，再考虑深度模型。

---

# 23. 项目与 ReactSeq、Synthelite、SynthEx 的关系

```text
ReactSeq
解决：一次反应怎样写成适合 Transformer 学习的反应语言

Synthelite
解决：LLM 怎样用自然语言意图引导模板搜索

SynthEx
解决：LLM 怎样先制定战略，再直接写图编辑并修改完整路线

SynthAudit
解决：不同系统的输出怎样统一执行、比较、审计并暴露不确定性
```

因此 SynthAudit 是下游 audit layer，不与这些生成系统做完全相同的工作。

---

# 24. 向导师介绍项目的两分钟版本

> SynthAudit 是一个面向异构逆合成表示的独立审核层。我把 mapped reaction SMILES、ReactSeq 和 agent-authored graph edits 归一为版本化 ReactionIR，再用事务式 RDKit 执行器把 reaction centre、synthon completion 和 stereochemistry 分阶段执行。系统将 deterministic representation validity、corpus novelty、precedent support 和 calibrated evidence 明确分开，因此不会把数据库中罕见的反应自动当作不可行。当前直接使用模式不需要训练模型；研究模式可在 parent-grouped 数据上训练分阶段、可校准、可 abstain 的 evidence models。

---

# 25. 最重要的使用原则

```text
先确认输入和 atom mapping
→ 再看执行是否成功
→ 再看 deterministic audit
→ 再看 novelty 和 precedent
→ 最后才看模型 evidence
→ 任何时候都保留人工与实验验证
```

这既是项目正确的阅读顺序，也是避免 AI 化学结果被过度解读的关键。
