# osi-model-generator-skill

一个用于生成、校验、可视化 **OSI（Open Semantic Interoperability）语义模型** 的 Skill 包。它把"业务对象/指标/关系/动作"闭环快速落到符合 OSI Core v0.1.2 规范的 `semantic_model` YAML，并以官方 `validate.py` 作为最终门禁。

> 核心 Skill 入口：[`SKILL.md`](./SKILL.md)

---

## 它能做什么

- **建模**：依据用户的业务场景/数据源描述，生成对齐 `bundled_osi/core-spec/osi-schema.json` 的 OSI YAML（datasets / relationships / metrics）。
- **行为层（可选）**：补齐 `semantic_model.behavior` 的 actions / rules / effects，用于确定性 action planning、归因解释与工程化校验。
- **门禁校验**：一键调用 `bundled_osi/validation/validate.py` 做 schema、唯一性、引用、SQL 语法多维校验。
- **可视化**：将 `references/templates/osi_ontology_viewer.html` 与 YAML 同目录分发，浏览器打开后可导入 YAML 渲染本体图谱（datasets / relationships / metrics / actions / rules）。

---

## 目录结构

```
osi-model-generator-skill/
├── SKILL.md                              # 主 Skill（生成/校验/可视化协议）
├── README.md                             # 当前文件
├── README_BUNDLE.md                      # 离线分发说明
├── behavior-layer.md                     # 行为层扩展规范（说明）
├── behavior-layer.schema.json            # 行为层 JSON Schema
├── test-prompts.json                     # Skill 触发/回归测试用 prompt 集
├── bundled_osi/
│   ├── core-spec/
│   │   ├── spec.md                       # OSI Core v0.1.2 规范文档
│   │   ├── spec.yaml                     # 规范 YAML 视图
│   │   ├── osi-schema.json               # OSI Core JSON Schema（version: const "0.1.2"）
│   │   ├── behavior-layer.md             # 行为层规范（bundle 副本）
│   │   └── behavior-layer.schema.json    # 行为层 schema（bundle 副本）
│   └── validation/
│       └── validate.py                   # 官方校验脚本
└── references/
    ├── examples/                         # 参考示例（restaurant_ops_min / sap_p2p_min / dtp / actions / rules）
    └── templates/
        ├── osi_core_skeleton.yaml        # OSI 最小骨架模板
        └── osi_ontology_viewer.html      # 单页可视化模板（导入 YAML 后渲染图谱）
```

---

## 快速开始

### 1. 安装依赖

```bash
pip install pyyaml jsonschema sqlglot
```

- `pyyaml`、`jsonschema`：必须
- `sqlglot`：可选，用于 SQL 表达式语法校验；不装也能跑，但会跳过 SQL 校验

### 2. 校验一个 OSI YAML

```bash
python bundled_osi/validation/validate.py references/examples/restaurant_ops_min.yaml --summary
```

校验项：

- **Schema**：结构、类型、枚举（`version` 必须为 `"0.1.2"`）
- **唯一性**：dataset / field / metric / relationship 重名
- **引用**：relationship 的 `from`/`to` 是否指向已有 dataset
- **SQL**：metric / field 表达式语法（依赖 `sqlglot`）

### 3. 可视化一个 OSI 模型

1. 把 `references/templates/osi_ontology_viewer.html` 复制到与目标 YAML **同目录**
2. 浏览器打开该 HTML
3. 右上角「导入 OSI YAML」选择该 YAML 即可渲染图谱

---

## 在 AI 助手中作为 Skill 使用

`SKILL.md` 头部的 frontmatter 描述了触发词和工作流。当用户说出以下任一意图时，Skill 会被激活：

- "生成 OSI 模型"、"按 OSI 规范输出 YAML"、"把这个语义模型改成 OSI"
- "根据业务场景建模 semantic_model"、"补齐 datasets/relationships/metrics"
- "为语义模型补 actions / rules（行为层）"
- "生成本体可视化页面"、"OSI 图谱展示"、"D3 本体图谱"

Skill 的工作流（详见 `SKILL.md`）：

1. **Step 0**：用例闭环拆解（对象 / 身份 / 关系 / 信号 / 动作 / 影响 / 门禁 / 回流）
2. **Step 0.5**：行为层放置选择（first-class `semantic_model.behavior` vs legacy `custom_extensions` 嵌入）
3. **Step 1–5**：生成 OSI Core 骨架 → datasets → relationships → metrics
4. **Step 6**：行为层（actions / rules / effects）
5. **Step 7**：门禁校验（必须跑 `validate.py`）
6. **Step 8**：生成可视化 HTML（与 YAML 同目录）

---

## OSI Core v0.1.2 关键约束（速查）

> 完整定义见 [`bundled_osi/core-spec/osi-schema.json`](./bundled_osi/core-spec/osi-schema.json) 与 [`bundled_osi/core-spec/spec.md`](./bundled_osi/core-spec/spec.md)。

- 顶层 `version` 必须 **严格等于** `"0.1.2"`（schema `const`）
- 顶层 `additionalProperties: false`：仅允许 `version` / `dialects` / `vendors` / `semantic_model`
- `semantic_model` 是数组；每个元素必须含 `name` 与 `datasets`，`datasets` `minItems: 1`
- `SemanticModel` / `Dataset` / `Field` / `Relationship` / `Metric` 均 `additionalProperties: false`，扩展统一走 `custom_extensions[]` 或 `semantic_model.behavior`
- `Expression.dialects` 至少 1 项；`DialectExpression` 仅 `dialect` + `expression`
- `CustomExtension` 仅 `vendor_name`（枚举：`COMMON`/`SNOWFLAKE`/`SALESFORCE`/`DBT`/`DATABRICKS`）+ `data`（**JSON 字符串**）
- `behavior`：`namespace` / `behavior_layer_version` / `actions` / `rules` 都必填（均允许空数组；旧别名 `action_types` 已移除）
- `Field.type`（可选）：逻辑属性类型枚举，作为 DB 映射锚点：`String` / `Number` / `Integer` / `Boolean` / `Date` / `DateTime` / `Time` / `JSON` / `Array`

---

## 参考示例

- [`references/examples/restaurant_ops_min.yaml`](./references/examples/restaurant_ops_min.yaml)：餐饮经营分析最小骨架
- [`references/examples/sap_p2p_min.yaml`](./references/examples/sap_p2p_min.yaml)：SAP P2P 缺料预警 + 行为层
- [`references/examples/dtp_semantic_model.yaml`](./references/examples/dtp_semantic_model.yaml)：完整 DTP 语义模型
- [`references/examples/actions.yaml`](./references/examples/actions.yaml) / [`rules.yaml`](./references/examples/rules.yaml)：行为层 actions / rules 参考集

---

## 许可

参见各文件中的版权与许可声明。OSI 规范及 `validate.py` 来自 [Open Semantic Interchange](https://github.com/open-semantic-interchange/OSI) 项目。
