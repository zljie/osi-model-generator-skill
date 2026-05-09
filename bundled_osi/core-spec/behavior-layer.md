# OSI 扩展规范：行为层（Actions & Rules）

**适用范围：** OSI Core v0.1.2 的补充扩展规范  
**目标：** 在不破坏 OSI Core 兼容性的前提下，引入“可执行语义（behavior layer）”，并将 **actions** 与 **rules** 两个节点结构化分离，用于确定性 action planning、归因解释（what changed/why）与工程化校验。

> OSI Core 规范见：[/core-spec/spec.md](file:///Users/johnson_mac/code/OSI/core-spec/spec.md)

---

## 1. 兼容性与放置位置

### 1.1 放置位置（两种等价放置）

本扩展支持两种放置方式：
1) **推荐（first-class）**：放在 `semantic_model.behavior`
2) **兼容（legacy）**：以 embedding 方式放在 `dataset.custom_extensions`

当使用 legacy embedding 方式时：
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
            "actions": [],
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
| `actions` | array | 是 | 动作定义列表（允许空数组） |
| `rules` | array | 是 | 规则定义列表（允许空数组） |
| `metadata` | object | 否 | 可选元信息（owner/tags/last_updated 等） |

约束：
- `actions` 与 `rules` 必须存在（允许为空数组）
- 未识别字段应被视为“保留字段”，导入导出时不得丢失（便于演进）

---

## 3. Actions（动作节点）

### 3.1 目的

Action 用于描述：对当前 dataset（或其 field/metric/relationship）**可执行的标准化动作**。  
典型用途：
- Agent/工具选择可执行能力（“能做什么”）
- 参数化调用（输入/输出 schema）
- RAG 检索增强（examples/tags/synonyms）

### 3.2 结构（推荐）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `id` | string | 是 | 全局唯一标识（建议 `dataset/action` 或 UUID） |
| `title` | string | 是 | 面向用户短标题 |
| `description` | string | 否 | 动作说明（业务语义） |
| `applies_to` | object | 否 | 动作作用对象（dataset/field/metric/relationship） |
| `io_schema` | object | 否* | 输入输出 JSON Schema（建议 draft 2020-12） |
| `examples` | string[] | 否 | 自然语言触发示例（利于召回） |
| `tool_hint` | object | 否 | 映射到工具/函数/方言提示 |
| `effects` | array | 否 | **影响注解**：该动作对 dataset/field/metric/relationship 的读写/推导影响（用于规划严谨性与归因） |
| `tags` | string[] | 否 | 能力标签 |
| `synonyms` | string[] | 否 | 动作别名（利于召回） |
| `deprecated` | boolean | 否 | 是否弃用 |
| `version` | string | 否 | 动作自身版本 |

\*MVP 建议必填：`io_schema.input_schema`（即使 output_schema 缺省）。

### 3.4 面向传统后端（ORM/CRUD）的推荐扩展字段

如果你希望 `actions` 能承载“传统开发后端中的 ORM 对象管理能力”，推荐为 Action 增加以下字段（**非 OSI Core**，属于行为层扩展内部字段，向后兼容）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `kind` | enum | `command`（写） / `query`（读） |
| `operation` | enum | `create/read/update/delete/list/search/upsert`（以及 `batch_*`） |
| `aggregate` | string | DDD 聚合名（例如 `Order`/`Opportunity`/`Loan`） |
| `entity_name` | string | ORM 实体名（通常等于 dataset.name 或业务对象名） |
| `idempotency` | enum | `idempotent` / `non_idempotent` / `unknown` |

建议约束：
- `id` 作为稳定引用键，尽量不使用中文；中文展示放在 `title`。
- 写操作统一为 `kind: command`；读操作统一为 `kind: query`。
- “列表/检索”与“读取单条”分开：`list/search` vs `read`。

### 3.5 CRUD Action 目录（建议每个聚合至少具备）

以下是推荐的“最小 CRUD 套件”，适用于多数业务对象：

- **Create（创建）**
  - `operation: create`：创建一条记录（命令）
- **Read（读取）**
  - `operation: read`：按主键读取单条（查询）
  - `operation: list`：分页列表（查询）
  - `operation: search`：条件检索（查询）
- **Update（更新）**
  - `operation: update`：按主键更新（命令）
  - `operation: upsert`：按自然键/业务键写入（命令，可选）
- **Delete（删除/归档）**
  - `operation: delete`：删除（命令）
  - 生产系统更推荐：`archive/deactivate` 代替硬删除

对于高频批量能力可补充：
- `batch_create`、`batch_update`、`batch_delete`

### 3.6 DDD 聚合服务（Domain Service / Application Service）动作建模

当动作不是简单 CRUD，而是“领域语义下的业务接口”（例如审批、收货过账、关单、续借等），推荐：

- `operation` 使用 **动词语义**（例如 `approve_po`、`post_goods_receipt`、`close_won`、`renew_loan`）
- `aggregate` 指向聚合根（例如 `PurchaseOrder`、`Opportunity`、`Loan`）
- `kind` 一般为 `command`
- 在 `io_schema.input_schema` 中明确必填参数与约束，尽量 `additionalProperties: false`

这能让你的 actions 成为“可检索、可计划、可校验”的接口目录（更接近 Palantir Ontology 的 action types），同时不破坏 OSI Core 的可移植性。

### 3.3 applies_to（可选）

```json
{
  "entity": "dataset",
  "selectors": {
    "field_names": ["order_id"],
    "metric_names": ["gross_revenue"],
    "relationship_names": ["orders_to_customers"]
  }
}
```

约束建议：
- 当 `entity != dataset` 时才需要 `selectors`
- selectors 仅做“引用”，不可替代 OSI Core 的 field/metric/relationship 定义

---

## 4. Rules（规则节点）

### 4.1 目的

Rule 用于描述：对 dataset（及其字段/指标/关系）施加的 **约束、治理、默认口径、质量要求与安全要求**。  
典型用途：
- 编辑器即时提示/阻止错误
- 校验报告解释“为什么不通过”
- Agent 生成 SQL/指标时做 grounding（避免口径漂移）

### 4.2 结构（推荐）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `id` | string | 是 | 全局唯一标识 |
| `title` | string | 是 | 规则短标题 |
| `description` | string | 否 | 规则说明 |
| `severity` | enum | 是 | `error`/`warn`/`info` |
| `when` | object | 是 | 适用范围（entity + selectors） |
| `if` | object | 否 | 可选条件（any_of/all_of/not） |
| `constraint` | object | 是 | 约束主体（type + 结构化限制） |
| `message` | string | 是 | 面向用户/Agent 的提示文本 |
| `remediation` | string | 否 | 修复建议 |
| `references` | array | 否 | 参考链接（可选） |
| `tags` | string[] | 否 | 标签 |

### 4.3 constraint.type（建议枚举）

- `naming`：命名/格式规则（例如 snake_case）
- `expression`：表达式限制（例如禁止聚合出现在 field）
- `join`：关系/键约束（例如 to_columns 必须指向唯一键）
- `filter`：默认过滤/口径约束（例如营收默认仅已支付）
- `security`：安全约束（例如 PII 不可用于输出）
- `quality`：质量要求（例如必填字段/行级唯一性）
- `other`：兜底

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
