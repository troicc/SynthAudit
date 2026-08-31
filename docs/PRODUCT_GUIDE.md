# SynthAudit 产品使用与复现指南

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.

本指南面向需要在本地审计单步反应、路线或不同反应表示的使用者。核心功能离线运行；未配置的语料、模型和提供者会明确返回 `unavailable`，不会生成看似合理的占位分数。

## 五分钟完成一次离线审计

```bash
make install
make product-examples
uv run synthaudit audit-reaction \
  --input examples/reaction-ir.json \
  --html /tmp/synthaudit-reaction.html \
  --json /tmp/synthaudit-reaction-audit.json
uv run synthaudit audit-route \
  --input examples/route-ir.json \
  --html /tmp/synthaudit-route.html \
  --json /tmp/synthaudit-route-audit.json
```

两个 HTML 文件均为单文件报告：CSS 和 RDKit SVG 已嵌入，不依赖服务器或外部字体；同目录 JSON sidecar 保存完整版本化输入、审计结果、限制和 provenance。如果默认 sidecar 会覆盖输入 JSON，CLI 自动改用 `.report.json` 后缀。

## 选择正确的入口

| 目标 | 入口 | 输出与失败语义 |
|---|---|---|
| ReactSeq 转 ReactionIR | `parse-reactseq` | 只接受已核验安全子集；需要显式映射产品；解析失败返回非零 |
| 映射反应或草案格式归一化 | `normalize-reaction` | 必须声明表示类型；不自动映射、不修复结构 |
| 分阶段执行 | `execute-reaction` | 保留中心、补全、立体阶段及 RDKit 错误；执行失败返回非零 |
| 跨表示语义比较 | `compare-representations` | 比较归一化图编辑与前体集合，不比较原始字符串 |
| 单步审计 | `audit-reaction` | 结构、中心、补全、立体结果相互独立；blocking 返回非零 |
| 路线审计 | `audit-route` | 输出依赖、连续性、条件、关键步骤与专家队列；不输出路线成功概率 |
| 先例与新颖性 | `precedent search` / `novelty score` | 需要本地版本化索引；六轴先例与多视图新颖性不合并成可行性 |
| 数据与模型 | `data ...` / `train` / `evaluate` | 显式清单、校验和、许可、分组划分与信任边界 |
| 报告与交互界面 | `report` / `ui` | HTML 可离线打印；UI 有五个页面且不承载核心算法 |

完整参数以 `synthaudit COMMAND --help` 为准。

## 使用五页交互工作区

```bash
make ui
```

默认只监听 `127.0.0.1:8501`。五个页面分别是：

1. **Representation Explorer**：表示归一化、ReactSeq token-to-atom 映射、编辑表与语义 round-trip；
2. **Single Reaction Audit**：产品/前体、四阶段审计、新颖性、先例、证据和不确定性；
3. **Route Audit**：策略、依赖图、连续性、条件冲突、逐步告警与专家队列；
4. **Benchmark**：只运行已提交的离线夹具并标示哪些研究指标仍为 `not_run`；
5. **Methodology and Limitations**：定义、来源、非实验边界与已知限制。

无需启动服务器即可验证页面依赖和数量：

```bash
make ui-smoke
```

## 准备本地先例索引

每行输入必须是严格的 `ReferenceReactionV1` JSON，并保留来源反应 ID、许可状态和 ReactionIR：

```bash
uv run synthaudit data prepare \
  --records /path/to/references.jsonl \
  --output /path/to/reference-index.json \
  --corpus-id my-corpus \
  --corpus-version 2026-08-31 \
  --json /tmp/index-build.json
```

索引保存记录 SHA-256、指纹规格、RDKit/SynthAudit 版本和来源许可。空索引或缺失视图返回 unavailable，而不是默认新颖性值。

## 训练与评估证据模型

`train` 只使用 `train` 分区拟合编码器和估计器，并只使用父组不重叠的 `calibration` 分区校准。`evaluate` 不参与阈值选择：

```bash
uv run synthaudit train \
  --examples evidence.jsonl \
  --artifact artifacts/centre.pkl \
  --stage reaction_centre_supported \
  --estimator logistic_regression \
  --calibration platt \
  --json artifacts/centre-train.json

uv run synthaudit evaluate \
  --examples evidence.jsonl \
  --artifact artifacts/centre.pkl \
  --manifest artifacts/centre.manifest.json \
  --trust-model-artifact \
  --split test \
  --scope research_benchmark \
  --json artifacts/centre-evaluation.json
```

pickle 只适用于来源可信且 SHA-256 匹配的本地模型；它不是跨环境稳定的发布格式，也不会在导入时加载。

## 证据、结论与复现路径

| Evidence | Finding | Reproduction path |
|---|---|---|
| `examples/*.json` 与 `reports/examples/*` | 产品流程可完全离线执行，报告包含 embedded SVG 和 sidecar | `make product-examples` 后检查 Git diff 应为空 |
| 200 条反事实夹具与 40 条提示变体 | 这是内容寻址的软件验证数据，不是性能或实验结果 | `make benchmark-small prompt-benchmark-small` |
| 3 条固定 ReactSeq demo | 当前安全子集对这三条的解析/执行/重构观察可重复 | `make reactseq-conformance-small` |
| 五页 Streamlit AppTest | 所有页面可在当前锁定环境启动，无需网络 | `pytest tests/integration/test_streamlit_pages.py` |
| 完整质量门 | 格式、lint、strict mypy、测试覆盖与所有小型烟测 | `make reproduce-small` |

研究尺度 AUROC、AUPRC、Brier、ECE、false rejection、selective risk、prompt robustness 等结果未预填；只有在 Phase 12 配置了合规数据与真实实验后才能发布。

## 排查常见失败

| 症状 | 原因与处理 |
|---|---|
| `AtomMappingRequired` | 输入缺失或混合映射；先在上游显式生成并审核映射，SynthAudit 不代填 |
| official SynthEx schema unavailable | 当前上游未发布 ReactionJSON/RouteJSON；只可显式选择 `synthaudit.synthex-paper-draft/0.1` |
| remote data access is disabled | 审阅 manifest、许可和 SHA-256 后，显式添加 `--allow-network` |
| pickle loading can execute code | 仅对可信本地产物使用 `--trust-model-artifact`，且保留 descriptor |
| report 返回 unavailable | 缺少语料、先例、模型或校准证据；这不是负面化学结论 |
