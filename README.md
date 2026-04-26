# ReleaseLens

Multi-agent pipeline that ingests Python packaging PEPs, reconciles them against real implementations across PyPI Warehouse, `pip`, and `uv`, and produces an impact report against a target codebase served by a pluggable artifact registry.

For the full system spec, see [`docs/architecture.md`](docs/architecture.md). For code-generation conventions, see [`AGENTS.md`](AGENTS.md).

## Quickstart

```bash
make setup
uv run releaselens --help
make demo
```
