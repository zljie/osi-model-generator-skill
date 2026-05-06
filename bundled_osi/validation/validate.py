#!/usr/bin/env python3
"""
OSI Semantic Model Validator

Validates OSI YAML files against:
1. JSON Schema (structure, types, enums)
2. Unique names (datasets, fields, metrics, relationships)
3. Valid relationship references
4. SQL syntax (using sqlglot)

Usage:
    python validation/validate.py <yaml_file>
    python validation/validate.py examples/tpcds_semantic_model.yaml

Optional outputs:
    python validation/validate.py examples/tpcds_semantic_model.yaml --summary
    python validation/validate.py examples/tpcds_semantic_model.yaml --emit-metric-sql
    python validation/validate.py examples/tpcds_semantic_model.yaml --emit-metric-sql --dialect SNOWFLAKE
    python validation/validate.py examples/library_semantic_model.yaml --emit-grouped-metric-sql --metric total_loans --group-by date_dim.quarter_name
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sqlglot: Any
ParseError: Any

try:
    import yaml
    from jsonschema import Draft202012Validator
except ImportError:
    print("Missing dependencies. Install with:")
    print("  pip install pyyaml jsonschema")
    sys.exit(1)

try:
    import sqlglot
    from sqlglot.errors import ParseError
    SQLGLOT_AVAILABLE = True
except ImportError:
    SQLGLOT_AVAILABLE = False
    sqlglot = None
    ParseError = Exception

# Map OSI dialects to sqlglot dialects
DIALECT_MAP = {
    "ANSI_SQL": None,  # sqlglot default
    "SNOWFLAKE": "snowflake",
    "DATABRICKS": "databricks",
    "MDX": None,  # Not supported by sqlglot, skip validation
    "TABLEAU": None,  # Not supported by sqlglot, skip validation
}

# Dialects that sqlglot cannot parse
SKIP_SQL_VALIDATION = {"MDX", "TABLEAU"}


def validate_schema(data: dict, schema: dict) -> list[str]:
    """Validate against JSON Schema."""
    validator = Draft202012Validator(schema)
    errors = []
    for error in validator.iter_errors(data):
        path = " -> ".join(str(p) for p in error.absolute_path) if error.absolute_path else "(root)"
        errors.append(f"[Schema] {path}: {error.message}")
    return errors


def find_duplicates(items: list[str]) -> list[str]:
    """Find duplicate items in a list."""
    seen = set()
    duplicates = []
    for item in items:
        if item in seen:
            duplicates.append(item)
        seen.add(item)
    return duplicates


def validate_unique_names(data: dict) -> list[str]:
    """Validate unique names for datasets, fields, metrics, relationships."""
    errors = []

    for model in data.get("semantic_model", []):
        model_name = model.get("name", "<unnamed>")

        # Check unique dataset names
        dataset_names = [d.get("name") for d in model.get("datasets", []) if d.get("name")]
        for dup in find_duplicates(dataset_names):
            errors.append(f"[Unique] Duplicate dataset name '{dup}' in model '{model_name}'")

        # Check unique field names within each dataset
        for dataset in model.get("datasets", []):
            dataset_name = dataset.get("name", "<unnamed>")
            field_names = [f.get("name") for f in dataset.get("fields", []) if f.get("name")]
            for dup in find_duplicates(field_names):
                errors.append(f"[Unique] Duplicate field name '{dup}' in dataset '{dataset_name}'")

        # Check unique metric names
        metric_names = [m.get("name") for m in model.get("metrics", []) if m.get("name")]
        for dup in find_duplicates(metric_names):
            errors.append(f"[Unique] Duplicate metric name '{dup}' in model '{model_name}'")

        # Check unique relationship names
        rel_names = [r.get("name") for r in model.get("relationships", []) if r.get("name")]
        for dup in find_duplicates(rel_names):
            errors.append(f"[Unique] Duplicate relationship name '{dup}' in model '{model_name}'")

    return errors


def validate_references(data: dict) -> list[str]:
    """Validate that relationships reference existing datasets."""
    errors = []

    for model in data.get("semantic_model", []):
        model_name = model.get("name", "<unnamed>")
        dataset_names = {d.get("name") for d in model.get("datasets", []) if d.get("name")}

        for rel in model.get("relationships", []):
            rel_name = rel.get("name", "<unnamed>")
            from_ds = rel.get("from")
            to_ds = rel.get("to")

            if from_ds and from_ds not in dataset_names:
                errors.append(f"[Reference] Relationship '{rel_name}' references unknown dataset '{from_ds}'")
            if to_ds and to_ds not in dataset_names:
                errors.append(f"[Reference] Relationship '{rel_name}' references unknown dataset '{to_ds}'")

    return errors


def validate_sql_expression(expr: str, dialect: str, context: str) -> str | None:
    """Validate a single SQL expression. Returns error message or None if valid."""
    if not SQLGLOT_AVAILABLE:
        return None
    assert sqlglot is not None

    if dialect in SKIP_SQL_VALIDATION:
        return None

    sqlglot_dialect = DIALECT_MAP.get(dialect)

    try:
        # Try parsing as expression first (for field expressions like "column_name")
        sqlglot.parse_one(expr, dialect=sqlglot_dialect)
        return None
    except ParseError:
        pass

    try:
        # Try wrapping in SELECT for simple column references
        sqlglot.parse_one(f"SELECT {expr}", dialect=sqlglot_dialect)
        return None
    except ParseError as e:
        return f"[SQL] {context}: {str(e).split(chr(10))[0]}"


def validate_sql(data: dict) -> list[str]:
    """Validate SQL expressions in fields and metrics."""
    if not SQLGLOT_AVAILABLE:
        return ["[SQL] Warning: sqlglot not installed, skipping SQL validation. Install with: pip install sqlglot"]

    errors = []

    for model in data.get("semantic_model", []):
        model_name = model.get("name", "<unnamed>")

        # Validate field expressions
        for dataset in model.get("datasets", []):
            dataset_name = dataset.get("name", "<unnamed>")
            for field in dataset.get("fields", []):
                field_name = field.get("name", "<unnamed>")
                expression = field.get("expression", {})
                for dialect_expr in expression.get("dialects", []):
                    dialect = dialect_expr.get("dialect", "ANSI_SQL")
                    expr = dialect_expr.get("expression", "")
                    if expr:
                        context = f"Field '{dataset_name}.{field_name}' ({dialect})"
                        error = validate_sql_expression(expr, dialect, context)
                        if error:
                            errors.append(error)

        # Validate metric expressions
        for metric in model.get("metrics", []):
            metric_name = metric.get("name", "<unnamed>")
            expression = metric.get("expression", {})
            for dialect_expr in expression.get("dialects", []):
                dialect = dialect_expr.get("dialect", "ANSI_SQL")
                expr = dialect_expr.get("expression", "")
                if expr:
                    context = f"Metric '{metric_name}' ({dialect})"
                    error = validate_sql_expression(expr, dialect, context)
                    if error:
                        errors.append(error)

    return errors


def _get_ai_context_examples(ai_context) -> list[str]:
    if not isinstance(ai_context, dict):
        return []
    examples = ai_context.get("examples")
    if isinstance(examples, list):
        return [str(x) for x in examples if x is not None]
    return []


def _get_ai_context_synonyms(ai_context) -> list[str]:
    if not isinstance(ai_context, dict):
        return []
    synonyms = ai_context.get("synonyms")
    if isinstance(synonyms, list):
        return [str(x) for x in synonyms if x is not None]
    return []


def _select_expression(expression_obj: dict, preferred_dialect: str) -> tuple[str | None, str | None]:
    dialects = expression_obj.get("dialects", []) if isinstance(expression_obj, dict) else []
    if not isinstance(dialects, list):
        return None, None

    for d in dialects:
        if isinstance(d, dict) and d.get("dialect") == preferred_dialect and isinstance(d.get("expression"), str):
            return d["expression"], preferred_dialect

    for d in dialects:
        if isinstance(d, dict) and d.get("dialect") == "ANSI_SQL" and isinstance(d.get("expression"), str):
            return d["expression"], "ANSI_SQL"

    for d in dialects:
        if isinstance(d, dict) and isinstance(d.get("expression"), str):
            return d["expression"], d.get("dialect")

    return None, None


def _build_dataset_index(model: dict) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for d in model.get("datasets", []) if isinstance(model, dict) else []:
        if not isinstance(d, dict):
            continue
        name = d.get("name")
        if isinstance(name, str) and name:
            out[name] = d
    return out


def _find_dataset_refs(expr: str, dataset_names: set[str]) -> list[str]:
    if not expr:
        return []
    candidates = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\.", expr)
    seen = set()
    refs = []
    for c in candidates:
        if c in dataset_names and c not in seen:
            seen.add(c)
            refs.append(c)
    return refs


def _build_relationship_edges(model: dict) -> list[tuple[str, str, list[str], list[str]]]:
    edges = []
    for rel in model.get("relationships", []) if isinstance(model, dict) else []:
        if not isinstance(rel, dict):
            continue
        a = rel.get("from")
        b = rel.get("to")
        from_cols = rel.get("from_columns")
        to_cols = rel.get("to_columns")
        if not (isinstance(a, str) and isinstance(b, str)):
            continue
        if not (isinstance(from_cols, list) and isinstance(to_cols, list)):
            continue
        if len(from_cols) != len(to_cols) or len(from_cols) == 0:
            continue
        edges.append((a, b, [str(x) for x in from_cols], [str(x) for x in to_cols]))
    return edges


def _find_join_path(
    edges: list[tuple[str, str, list[str], list[str]]],
    start: str,
    goal: str,
) -> list[tuple[str, str, list[str], list[str]]]:
    if start == goal:
        return []

    neighbors: dict[str, list[tuple[str, str, list[str], list[str]]]] = {}
    for a, b, a_cols, b_cols in edges:
        neighbors.setdefault(a, []).append((a, b, a_cols, b_cols))
        neighbors.setdefault(b, []).append((b, a, b_cols, a_cols))

    queue = [start]
    prev: dict[str, tuple[str, tuple[str, str, list[str], list[str]]]] = {}
    visited = {start}

    while queue:
        cur = queue.pop(0)
        for step in neighbors.get(cur, []):
            left, right, left_cols, right_cols = step
            if right in visited:
                continue
            visited.add(right)
            prev[right] = (cur, step)
            if right == goal:
                queue = []
                break
            queue.append(right)

    if goal not in prev:
        return []

    path: list[tuple[str, str, list[str], list[str]]] = []
    node = goal
    while node != start:
        _, step = prev[node]
        path.append(step)
        node = prev[node][0]
    path.reverse()
    return path


def _emit_metric_sql(model: dict, preferred_dialect: str) -> list[str]:
    dataset_index = _build_dataset_index(model)
    dataset_names = set(dataset_index.keys())
    edges = _build_relationship_edges(model)

    out = []
    for metric in model.get("metrics", []) if isinstance(model, dict) else []:
        if not isinstance(metric, dict):
            continue
        metric_name = metric.get("name", "<unnamed>")
        expr, used_dialect = _select_expression(metric.get("expression", {}), preferred_dialect)
        if not expr:
            out.append(f"- {metric_name}: (no expression)")
            continue

        refs = _find_dataset_refs(expr, dataset_names)
        base = refs[0] if refs else (model.get("datasets", [{}])[0].get("name") if model.get("datasets") else None)
        if not isinstance(base, str) or base not in dataset_index:
            out.append(f"- {metric_name} ({used_dialect}): (cannot determine base dataset)")
            continue

        base_source = dataset_index[base].get("source")
        if not isinstance(base_source, str):
            out.append(f"- {metric_name} ({used_dialect}): (base dataset '{base}' has no source)")
            continue

        joins = []
        joined = {base}

        for target in refs[1:]:
            if target in joined:
                continue
            path = _find_join_path(edges, base, target)
            for left, right, left_cols, right_cols in path:
                if right in joined:
                    continue
                right_ds = dataset_index.get(right, {})
                right_source = right_ds.get("source")
                if not isinstance(right_source, str):
                    continue
                conds = " AND ".join([f"{left}.{lc} = {right}.{rc}" for lc, rc in zip(left_cols, right_cols)])
                joins.append(f"LEFT JOIN {right_source} AS {right} ON {conds}")
                joined.add(right)

        sql = f"SELECT {expr} AS {metric_name}\nFROM {base_source} AS {base}"
        if joins:
            sql += "\n" + "\n".join(joins)
        sql += ";"

        out.append(f"- {metric_name} (dialect={used_dialect}, base={base})\n\n```sql\n{sql}\n```\n")

    return out


def _emit_grouped_metric_sql(
    model: dict,
    metric_name: str,
    group_by: str,
    preferred_dialect: str,
) -> str:
    dataset_index = _build_dataset_index(model)
    dataset_names = set(dataset_index.keys())
    edges = _build_relationship_edges(model)

    metric_obj = None
    for m in model.get("metrics", []) if isinstance(model, dict) else []:
        if isinstance(m, dict) and m.get("name") == metric_name:
            metric_obj = m
            break

    if metric_obj is None:
        return f"[Query SQL] metric '{metric_name}' not found"

    metric_expr, used_dialect = _select_expression(metric_obj.get("expression", {}), preferred_dialect)
    if not metric_expr:
        return f"[Query SQL] metric '{metric_name}' has no expression"

    metric_refs = _find_dataset_refs(metric_expr, dataset_names)
    group_refs = _find_dataset_refs(group_by, dataset_names)
    all_refs = []
    for r in metric_refs + group_refs:
        if r not in all_refs:
            all_refs.append(r)

    base = None
    if metric_refs:
        base = metric_refs[0]
    elif group_refs:
        base = group_refs[0]
    else:
        ds0 = (model.get("datasets") or [{}])[0]
        base = ds0.get("name") if isinstance(ds0, dict) else None

    if not isinstance(base, str) or base not in dataset_index:
        return f"[Query SQL] (cannot determine base dataset for metric '{metric_name}')"

    base_source = dataset_index[base].get("source")
    if not isinstance(base_source, str):
        return f"[Query SQL] (base dataset '{base}' has no source)"

    joins = []
    joined = {base}

    for target in all_refs:
        if target in joined:
            continue
        path = _find_join_path(edges, base, target)
        if not path:
            return f"[Query SQL] (no join path: base='{base}' -> target='{target}')"
        for left, right, left_cols, right_cols in path:
            if right in joined:
                continue
            right_ds = dataset_index.get(right, {})
            right_source = right_ds.get("source")
            if not isinstance(right_source, str):
                continue
            conds = " AND ".join([f"{left}.{lc} = {right}.{rc}" for lc, rc in zip(left_cols, right_cols)])
            joins.append(f"LEFT JOIN {right_source} AS {right} ON {conds}")
            joined.add(right)

    group_alias = "group_key"
    sql = f"SELECT {group_by} AS {group_alias}, {metric_expr} AS {metric_name}\nFROM {base_source} AS {base}"
    if joins:
        sql += "\n" + "\n".join(joins)
    sql += f"\nGROUP BY {group_by}\nORDER BY {group_by};"

    return f"[Query SQL] metric={metric_name}, group_by={group_by}, dialect={used_dialect}, base={base}\n\n```sql\n{sql}\n```"


def _print_summary(data: dict, verbose_ai: bool) -> None:
    for model in data.get("semantic_model", []):
        if not isinstance(model, dict):
            continue
        name = model.get("name", "<unnamed>")
        print(f"\n[Model] {name}")
        desc = model.get("description")
        if isinstance(desc, str) and desc.strip():
            print(f"  Description: {desc.strip()}")

        if verbose_ai:
            ai = model.get("ai_context")
            if isinstance(ai, dict):
                instr = ai.get("instructions")
                if isinstance(instr, str) and instr.strip():
                    print(f"  AI.instructions: {instr.strip()}")
                syns = _get_ai_context_synonyms(ai)
                if syns:
                    print(f"  AI.synonyms: {', '.join(syns[:12])}{' ...' if len(syns) > 12 else ''}")
                exs = _get_ai_context_examples(ai)
                for e in exs[:8]:
                    print(f"  AI.example: {e}")

        datasets = [d for d in model.get("datasets", []) if isinstance(d, dict)]
        print(f"  Datasets: {len(datasets)}")
        for d in datasets:
            dn = d.get("name", "<unnamed>")
            src = d.get("source", "")
            pk = d.get("primary_key")
            fields = d.get("fields", [])
            field_count = len(fields) if isinstance(fields, list) else 0
            pk_text = f" pk={pk}" if isinstance(pk, list) and pk else ""
            print(f"    - {dn}: source={src}{pk_text}, fields={field_count}")

        rels = [r for r in model.get("relationships", []) if isinstance(r, dict)]
        print(f"  Relationships: {len(rels)}")
        for r in rels:
            rn = r.get("name", "<unnamed>")
            fr = r.get("from", "")
            to = r.get("to", "")
            fc = r.get("from_columns", [])
            tc = r.get("to_columns", [])
            print(f"    - {rn}: {fr}{fc} -> {to}{tc}")

        metrics = [m for m in model.get("metrics", []) if isinstance(m, dict)]
        print(f"  Metrics: {len(metrics)}")
        for m in metrics:
            mn = m.get("name", "<unnamed>")
            md = m.get("description")
            if isinstance(md, str) and md.strip():
                print(f"    - {mn}: {md.strip()}")
            else:
                print(f"    - {mn}")


def main():
    parser = argparse.ArgumentParser(
        description="OSI Semantic Model Validator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("yaml_file", nargs="?", help="Path to an OSI semantic model YAML file")
    parser.add_argument("--summary", action="store_true", help="Print a semantic summary (datasets/relationships/metrics)")
    parser.add_argument("--ai", action="store_true", help="Include ai_context highlights in --summary output")
    parser.add_argument(
        "--emit-metric-sql",
        action="store_true",
        help="Emit SQL templates for metrics using relationships as LEFT JOINs",
    )
    parser.add_argument(
        "--emit-grouped-metric-sql",
        action="store_true",
        help="Emit a grouped SQL query for a metric (requires --metric and --group-by)",
    )
    parser.add_argument("--metric", help="Metric name for --emit-grouped-metric-sql")
    parser.add_argument("--group-by", dest="group_by", help="Group-by expression like date_dim.quarter_name")
    parser.add_argument(
        "--dialect",
        default="ANSI_SQL",
        help="Preferred dialect for SQL emission (fallback to ANSI_SQL)",
    )

    args = parser.parse_args()
    if not args.yaml_file:
        print(__doc__)
        sys.exit(1)

    yaml_path = Path(args.yaml_file)
    schema_path = Path(__file__).parent.parent / "core-spec" / "osi-schema.json"

    if not yaml_path.exists():
        print(f"Error: File not found: {yaml_path}")
        sys.exit(1)

    if not schema_path.exists():
        print(f"Error: Schema not found: {schema_path}")
        sys.exit(1)

    # Load files
    with open(schema_path) as f:
        schema = json.load(f)

    with open(yaml_path) as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(f"Error: Invalid YAML: {e}")
            sys.exit(1)

    # Run validations
    errors = []
    errors.extend(validate_schema(data, schema))
    errors.extend(validate_unique_names(data))
    errors.extend(validate_references(data))
    errors.extend(validate_sql(data))

    if args.summary:
        _print_summary(data, verbose_ai=args.ai)

    if args.emit_metric_sql:
        for model in data.get("semantic_model", []):
            if not isinstance(model, dict):
                continue
            model_name = model.get("name", "<unnamed>")
            print(f"\n[Metric SQL] model={model_name}, preferred_dialect={args.dialect}")
            blocks = _emit_metric_sql(model, preferred_dialect=args.dialect)
            if not blocks:
                print("  (no metrics)")
            else:
                for b in blocks:
                    print(b)

    if args.emit_grouped_metric_sql:
        if not args.metric or not args.group_by:
            print("Error: --emit-grouped-metric-sql requires --metric and --group-by")
            sys.exit(1)
        for model in data.get("semantic_model", []):
            if not isinstance(model, dict):
                continue
            model_name = model.get("name", "<unnamed>")
            print(f"\n[Grouped Query SQL] model={model_name}, preferred_dialect={args.dialect}")
            print(_emit_grouped_metric_sql(model, args.metric, args.group_by, preferred_dialect=args.dialect))

    # Report results
    if errors:
        # Separate warnings from errors
        warnings = [e for e in errors if "Warning:" in e]
        actual_errors = [e for e in errors if "Warning:" not in e]

        for warning in warnings:
            print(f"  {warning}")

        if actual_errors:
            print(f"\nValidation FAILED with {len(actual_errors)} error(s):\n")
            for error in actual_errors:
                print(f"  {error}")
            sys.exit(1)
        else:
            print(f"Validation PASSED: {yaml_path.name}")
            sys.exit(0)
    else:
        print(f"Validation PASSED: {yaml_path.name}")
        sys.exit(0)


if __name__ == "__main__":
    main()
