# OSI 扩展规范：行为层（Action Types & Rules）

**适用范围：** OSI Core v0.1.1 的补充扩展规范  
**目标：** 在不破坏 OSI Core 兼容性的前提下，为 `dataset` 引入“可执行语义（behavior layer）”，并将 **action_types** 与 **rules** 两个节点结构化分离，用于检索增强（RAG）、语义理解稳定性与工程化校验。

> OSI Core 规范见：[/core-spec/spec.md](file:///Users/johnson_mac/code/OSI/core-spec/spec.md)

---

## 1. 兼容性与放置位置

### 1.1 放置位置（dataset.custom_extensions）

本扩展以 **Embedding** 方式放入 OSI dataset：
- 不新增/修改 OSI Core 字段
- 使用 OSI Core 已定义的 `custom_extensions` 承载扩展数据

示例：

```yaml
datasets:
  - name: orders
    source: db.schema.orders
    custom_extensions:
      - vendor_name: COMMON
        data: |
          {
            "namespace": "PALANTIR",
            "behavior_layer_version": "0.1",
            "action_types": [],
            "rules": []
          }
```

### 1.2 vendor_name 约束

OSI Core v0.1.1 的 `vendor_name` 是枚举（`COMMON/SNOWFLAKE/SALESFORCE/DBT/DATABRICKS`）。  
因此当需要表达“PALANTIR/Foundry Ontology 风格”时，推荐：
- `vendor_name: "COMMON"`
- 在 `data.namespace` 指定 `PALANTIR`（或你的平台命名空间）

这样可保持对 OSI Core schema 的兼容性，同时让扩展有明确归属。

---

## 2. 顶层对象：BehaviorLayer（custom_extensions.data）

`custom_extensions.data` 内部建议使用 JSON（字符串）表示如下结构：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `namespace` | string | 是 | 命名空间（如 `PALANTIR` 或组织/平台名） |
| `behavior_layer_version` | string | 是 | 行为层扩展版本（如 `0.1`） |
| `action_types` | array | 是 | 动作类型定义列表（允许空数组） |
| `rules` | array | 是 | 规则定义列表（允许空数组） |
| `metadata` | object | 否 | 可选元信息（owner/tags/last_updated 等） |

约束：
- `action_types` 与 `rules` 必须同时存在（允许为空数组）
- 未识别字段应被视为“保留字段”，导入导出时不得丢失（便于演进）

---

## 3. Action Types（动作类型节点）

### 3.1 目的

ActionType 用于描述：对当前 dataset（或其 field/metric/relationship）**可执行的标准化动作**。  
典型用途：
- Agent/工具选择可执行能力（“能做什么”）
- 参数化调用（输入/输出 schema）
- RAG 检索增强（examples/tags/synonyms）

### 3.2 Action Types 结构（v0.2 对齐 OSI Core 命名）

与 OSI Core 规范保持一致的字段命名（`name` 而非 `title`，`ai_context` 结构对齐）。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `id` | string | ✅ | 全局唯一动作标识，建议 `{dataset}/{action}` 格式，如 `pr/create` |
| `name` | string | ✅ | 面向用户的短标题（展示用），如"创建采购申请" |
| `description` | string | - | 动作的业务语义说明 |
| `kind` | enum | ✅ | `command`（写操作）或 `query`（读/查询操作） |
| `entity_name` | string | - | 指向的逻辑数据集名（如 `purchase_requisitions`） |
| `io_schema` | object | - | 输入/输出 JSON Schema，建议包含 `input_schema` |
| `effects` | array | - | 动作副作用，定义对 dataset/field 的读写影响 |
| `ai_context` | string[] | - | 自然语言触发示例（利于 AI 召回） |
| `tool_hint` | object | - | 工具/方言映射提示 |
| `label` | string[] | - | 能力标签 |
| `synonyms` | string[] | - | 动作别名（利于召回） |
| `version` | string | - | 动作自身版本号 |


### 3.3 kind 枚举

| 字段 | 枚举值 | 说明 |
|---|---|---|
| `kind` | `command` | 写操作（创建/更新/删除/状态变更等） |
| `kind` | `query` | 读操作（查询/聚合/派生计算等） |

### 3.4 effects 子结构

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `entity` | enum | ✅ | `dataset` 或 `field` |
| `mode` | enum | ✅ | `write` / `derive` |
| `impact_type` | enum | ✅ | 影响类型（见下表） |
| `selectors` | object | ✅ | 作用对象选择器 |
| `set_value` | any | - | `state_transition` 时的新值 |

**impact_type 枚举：**

| 值 | 说明 |
|---|---|
| `create_row` | 创建行记录 |
| `update_row` | 更新行记录 |
| `delete_row` | 删除行记录 |
| `aggregate` | 聚合计算 |
| `compute` | 计算派生值 |
| `state_transition` | 状态变更 |

### 3.5 CRUD ActionType 目录

建议每个聚合至少具备以下最小 CRUD 套件：

- `create`：创建一条记录（command）
- `read`：按主键读取单条（query）
- `list`：分页列表（query）
- `search`：条件检索（query）
- `update`：按主键更新（command）
- `upsert`：按自然键/业务键写入（command，可选）
- `delete`：删除/归档（command）

---

## 4. Rules（规则节点）

### 4.1 目的

Rule 用于描述：对 dataset（及其字段/指标/关系）施加的 **约束、治理、默认口径、质量要求与安全要求**。  
典型用途：
- 编辑器即时提示/阻止错误
- 校验报告解释“为什么不通过”
- Agent 生成 SQL/指标时做 grounding（避免口径漂移）

### 4.2 Rules 结构（v0.2 对齐 OSI Core 命名）

与 OSI Core 规范保持一致的字段命名（`name` 而非 `title`，`ai_context` 作为提示文本）。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `id` | string | ✅ | 全局唯一规则标识，建议 `{namespace}/{rule_name}` 格式，如 `dtp/rule_no_po_without_approved_pr` |
| `name` | string | ✅ | 规则短标题（展示用），如"无申请不下单" |
| `description` | string | - | 规则的详细说明 |
| `severity` | enum | ✅ | `error`（阻止）/ `warn`（警告）/ `info`（提示） |
| `when` | object | ✅ | 规则触发时机，详见 when 子结构 |
| `if` | object | - | 可选条件（any_of / all_of / not），用于更细粒度触发控制 |
| `constraint` | object | ✅ | 约束主体，详见 constraint 子结构 |
| `ai_context` | string[] | - | 面向用户/Agent 的违规提示文本数组 |
| `references` | array | - | 参考链接列表（文档、流程等） |
| `label` | string[] | - | 规则标签 |

> **与 v0.1 的差异：**
> - `title` → `name`（与 OSI Core `name` 字段对齐）
> - `message` → `ai_context`（改为字符串数组，与 OSI Core 结构对齐）
> - `tags` → `label`（与 OSI Core `label` 字段对齐）
> - 移除 `operation`、`applies_to`（Action）、`remediation`（Rule）

### 4.3 when 子结构

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `entity` | enum | ✅ | `action` / `dataset` / `field` / `metric` / `relationship` |
| `applies_to` | object | - | 当 entity=action 时使用 |
| `applies_to.action_id` | string | - | 触发的动作ID，如 `po/create` / `gr/post` |
| `selectors` | object | - | 当 entity!=action 时使用 |
| `selectors.dataset` | string | - | 目标数据集名 |
| `selectors.field_names` | string[] | - | 目标字段名列表 |

### 4.4 constraint 子结构

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `type` | enum | ✅ | 约束类型（见下表） |
| `requires` | string[] | - | 必须满足的条件表达式列表 |
| `forbidden` | string[] | - | 禁止的条件表达式列表 |
| `equals` | any | - | 必须等于的值（如 `Pass`） |
| `pattern` | string | - | 正则表达式（用于 naming 类型） |
| `max_length` | number | - | 最大长度限制 |
| `min_length` | number | - | 最小长度限制 |
| `recommendation` | string | - | 策略建议文本（用于 warn 级别） |
| `refers_to` | string | - | 引用字段路径（用于 control 类型） |

**constraint.type 枚举：**

| 值 | 说明 | 典型用途 |
|---|---|---|
| `compliance` | 合规性硬约束 | 无申请不下单、无PO不收货 |
| `governance` | 治理约束 | 预算校验必过、字段必填 |
| `risk` | 风险控制约束 | 供应商准入、价格超限 |
| `policy` | 业务策略建议 | 利库优先、紧急采购需审批 |
| `control` | 内部控制 | 收货超允差、金额超额 |
| `naming` | 命名规范 | snake_case、前缀要求 |
| `expression` | 表达式约束 | 禁止聚合出现在 field |
| `filter` | 口径/过滤约束 | 默认仅统计已审批数据 |
| `security` | 安全约束 | PII 字段不可输出 |
| `quality` | 质量要求 | 行级唯一性、非空校验 |
| `other` | 兜底类型 | 其他未分类约束 |

### 4.5 if 子结构（可选条件）

用于更细粒度的规则触发控制：

```yaml
if:
  any_of:
    - { field: "purchase_requisitions.emergency_flag", equals: true }
    - { field: "purchase_requisitions.priority", equals: "URGENT" }
```

支持操作符：`any_of` / `all_of` / `not`

---

## 5. 与 OSI Core 的边界（重要）

为保持可移植性与互操作性：
- **必须**：核心语义仍由 OSI Core 表达（datasets/relationships/fields/metrics）
- **允许**：行为层补充“可执行能力与治理规则”
- **禁止**：把关键 join/关键口径完全挪到扩展里导致脱离 OSI Core 无法解释

---

## 6. 校验建议（工程内）

推荐为 `custom_extensions.data`（BehaviorLayer）提供独立 JSON Schema，用于：
- CI 校验
- 前端编辑器即时校验
- 导入时的错误提示定位

建议 schema 文件路径：
- `core-spec/behavior-layer.schema.json`
