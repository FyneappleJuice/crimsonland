---
name: ast-grep
description: Use ast-grep (`sg`) for Python structural code exploration, mechanical codemods, and rule maintenance in this repo. Use this when you need syntax-aware search/replace (instead of regex), to add/update ast-grep rules in `tools/ast-grep/`, or to verify rule behavior with `sg scan` and `sg test`.
---

# Ast-grep

Prefer `sg` for structural exploration and mechanical rewrites in Python code.

## Quick Start

- Run policy checks: `sg scan`
- Run rule tests + snapshots: `sg test`
- Run full local check chain: `just check`

## Structural Exploration

Use `sg run` with `-p` for ad-hoc structural queries.

Python examples:

```bash
sg run -l python -p 'config.data.get($$$ARGS)' src tests
sg run -l python -p 'except Exception: pass' src tests
```

## Mechanical Codemods

1. Start narrow (single directory or file set).
2. Prototype match/rewrite:

```bash
sg run -l python -p 'config.data.get($$$ARGS)' -r 'config.get($$$ARGS)' src
```

3. Apply intentionally:
- Interactive: add `-i`
- Apply all matches: add `-U`
4. Review `git diff` and rerun `sg scan` and `sg test`.

## Repo Rule Layout

- Main config: `sgconfig.yml`
- Main rules: `tools/ast-grep/rules/`
- Main tests: `tools/ast-grep/tests/`
- Shared utils: `tools/ast-grep/utils/`

Rules are YAML files with `id`, `language`, `severity`, `message`, path scope (`files`/`ignores`), and `rule` matcher. Keep `id`, rule filename, and test filename aligned.

## Repo Test Layout

Each test file mirrors a rule ID and includes:
- `valid`: examples that must not match
- `invalid`: examples that must match

Snapshot files live in `__snapshots__/` beside tests and are checked by `sg test`.

Useful commands:

```bash
# all configured tests
sg test

# one rule by id regex
sg test -f no-config-data-get

# refresh all snapshots after intentional rule changes
sg test -U
```

## Repo Policy Notes

From `CONTRIBUTING.md`:
- Prefer ast-grep over regex-only edits for structural transforms.
- When mistakes repeat, encode them as rules/tests/snapshots.
