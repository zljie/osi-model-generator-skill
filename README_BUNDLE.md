# OSI 模型生成器（可离线打包版）

本目录用于分发与离线使用：包含 Skill 本体 + OSI 规范/Schema + 校验脚本 `validate.py`。

## 目录结构（打包后）

- `SKILL.md`：主 Skill
- `references/`：模板与示例
- `bundled_osi/`：
  - `core-spec/`：OSI 核心规范与 JSON Schema
  - `validation/validate.py`：官方校验脚本（来自 OSI 仓库）

## 依赖

`validate.py` 依赖：
- `pyyaml`
- `jsonschema`
- （可选）`sqlglot`：用于 SQL 表达式语法校验；不装也能跑，但会跳过 SQL 校验或给 warning

安装示例：

```bash
pip install pyyaml jsonschema sqlglot
```

## 如何校验一个 OSI YAML

在包含 `bundled_osi/` 的目录下执行：

```bash
python bundled_osi/validation/validate.py <your_yaml_file> --summary
```

## 注意

- OSI Core v0.1.2 的 schema 对 `version` 有 const 约束；若你要兼容旧 UI（0.1.1），请在 Skill 中选择 v0.1.1 Profile（legacy embedding）。

