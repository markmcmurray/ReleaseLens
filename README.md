# ReleaseLens

Multi-agent pipeline that ingests Python packaging PEPs, reconciles them against real implementations across PyPI Warehouse, `pip`, and `uv`, and produces an impact report against a target codebase served by a pluggable artifact registry.

For the full system spec, see [`docs/architecture.md`](docs/architecture.md). For code-generation conventions, see [`AGENTS.md`](AGENTS.md).

## Quickstart

```bash
make setup                       # uv sync --all-extras
uv run releaselens --help
uv run releaselens run --pep-ids 658
```

The `run` command end-to-ends the pipeline against a bundled PEP-658 fixture and writes a Markdown report under `reports/`. The path is printed on completion alongside the `run_id` (use it with `releaselens resume <run_id>` to replay from the SQLite checkpoint at `.releaselens/checkpoints.db`).

### Optional system dependencies

The pipeline runs end-to-end without these — `evidence_static` will record a "static search skipped" note and the escalation ladder takes over — but you'll only see real `<tool>:<path>:<line>` source refs when both are present:

- **`ripgrep`** on `PATH`. Not a Python package, so it can't go in `pyproject.toml`. Install with the platform package manager:
  ```bash
  brew install ripgrep            # macOS
  apt-get install ripgrep         # Debian/Ubuntu
  ```
- **Local source clones** of the tools you want to grep. Defaults are `data/sources/{pip,uv,warehouse}/`; override the parent dir with `RELEASELENS_SOURCES_DIR=/path/to/clones`.
  ```bash
  mkdir -p data/sources
  git clone --depth 1 https://github.com/pypa/pip data/sources/pip
  git clone --depth 1 https://github.com/astral-sh/uv data/sources/uv
  git clone --depth 1 https://github.com/pypi/warehouse data/sources/warehouse
  ```

---

## Status

The scaffold is complete: every node, every edge, every schema, and every reducer in `docs/architecture.md` §3–§7 exists in code and the graph executes end-to-end. What varies is whether each node does *real* work or returns deterministic stub data sized to the schema.

### Done

**Core graph.** All 12 nodes wired in `src/releaselens/graph.py`, all five `Send` fan-out points (PEP, feature, test-author per claim, evidence per tool, impact per feature), the evidence-escalation conditional ladder, and the SqliteSaver checkpointer.

**Schemas & state.** All 11 Pydantic v2 record types under `src/releaselens/schemas/`. `PipelineState` TypedDict with `add` / `dict_merge` reducers on every fan-in field.

**LLM nodes that do real work.**
- `pep_ingest` — reads RST from `data/peps/`, parses sections via `releaselens.peps.rst`.
- `feature_extract` — Nova Pro decomposition into atomic `Feature`s + `SpecClaim`s.
- `test_author` / `critic` — evaluator-optimizer loop with retry budget and feedback piping (ADR-0007), routed asymmetrically (Pro author, Lite critic).

**Deterministic Python nodes (no LLM).** `evidence_aggregate`, `matrix_build`, `verify`, `impact_scope`, `report_render`.

**Tooling layer.** Real implementations with stub-mode parity selected via `RELEASELENS_<TOOL>_MODE`:
- `tools/ripgrep.py` — streaming stdout wrapper.
- `tools/github.py` — commit-archaeology via PyGithub.
- `tools/rag.py` — ChromaDB collections backed by Bedrock Titan embeddings.
- `tools/uv_sandbox.py` — per-invocation `uv venv` lifecycle.
- `tools/differential_runner.py` — three executors (`static_signature`, `behavioural_probe`, `metadata_assertion`); no LLM in the runner path.

**LLM gateway & routing.** LiteLLM call wrapper with cassette record/replay (`src/releaselens/llm.py`); per-node model selection from `config/model_routing.yaml` (currently Amazon Nova family — see the file header for the rationale).

**Observability.** Langfuse self-host docker compose at `infra/langfuse/`; tracing wired through three seams (LiteLLM callback for generations, LangGraph `CallbackHandler` for node spans, `tool_span` context manager around each tool wrapper). All seams are no-ops without `LANGFUSE_*` env vars. See "See it in action" §5 for the walkthrough.

**CLI.** `releaselens run | resume | eval` with click; `run` auto-copies the bundled PEP fixture into `data/peps/` if missing.

**Tests.** Unit tests for the loop nodes, RST parser, smoke tests, integration scaffolding; recorded LiteLLM cassettes under `tests/cassettes/`.

### Not done

The gap between scaffold-complete and architecture-complete is the [§19 done-state checklist](docs/architecture.md#19-done-state-checklist-for-the-implementer). The headline gaps:

- **Evidence nodes still produce stub records.** `evidence_static`, `evidence_changelog`, `evidence_probe` return deterministic `ImplementationEvidence` instances with `version_first_seen="0.0.0-stub"` rather than wiring the existing tool layer through. The tools exist; the nodes don't call them yet.
- **`DevpiPublicConnector` is synthetic.** Returns canned `ResolvedArtefact`s; no HTTP traffic to a real devpi.
- **Only PEP-658 has a fixture.** PEP-691 and PEP-740 are referenced by `make demo` but no RST is bundled. Running `--pep-ids 691,740` will fail at ingest.
- **Eval harness is a stub.** `eval/runner.py` and `eval/score.py` are placeholders; `data/fixtures/` is empty; `releaselens eval` short-circuits with a "no fixtures" message. Precision/recall/F1 against ground-truth is the next major chunk of work.
- **No ADRs committed under `docs/adr/`** despite ADR-0001 through ADR-0007 being referenced throughout the spec.
- **No `docs/cost_model.md`** with per-stage figures from a baseline run.
- **`tests/integration/` is empty** — failure-mode coverage from architecture §12.3 not yet exercised.

---

## See it in action

### 1. End-to-end pipeline run

```bash
make setup
uv run releaselens run --pep-ids 658
```

What to look for:
- Console prints `run_id: <uuid>` and `report: reports/<run_id>/report.md`.
- The report has Spec / Reality / Impact sections per Feature; the Reality columns will say `version_first_seen=0.0.0-stub` because the evidence nodes are scaffolded — that's expected and the visible boundary of "done vs not done."
- A SQLite checkpoint database appears at `.releaselens/checkpoints.db`.

### 2. Resume from a checkpoint

```bash
uv run releaselens resume <run_id>      # the run_id printed above
```

Confirms `SqliteSaver` is wired and the graph compiles against persisted state.

### 3. Test-author / critic loop

```bash
uv run pytest tests/unit/test_loop_integration.py -v
```

Drives the `test_author` → `critic` → `test_author` retry loop using recorded Nova cassettes from `tests/cassettes/`. To re-record against live Bedrock, delete the relevant cassette and re-run with AWS credentials present.

### 4. Tool wrappers in real mode

```bash
RELEASELENS_RIPGREP_MODE=real uv run python -c "from releaselens.tools.ripgrep import search; \
  [print(line) for line in search(['Feature'], ['src/releaselens/schemas'])]"

RELEASELENS_RAG_MODE=real uv run python -c "from releaselens.tools.rag import PEPCollection; \
  c = PEPCollection(); c.upsert('pep-658', 'metadata files via Warehouse'); print(c.query('metadata'))"
```

Stub mode (the default in tests) returns canned data registered per call key; unregistered keys raise `StubNotRegistered` so silent zero-result replays can't mask bugs.

### 5. Walkable trace via self-hosted Langfuse

Tracing is no-op until the three `LANGFUSE_*` env vars are set, so tests stay infra-free. To see a run end-to-end:

```bash
# 1. start Postgres + Langfuse via docker compose
make langfuse-up

# 2. open http://localhost:3000, create a local user + organisation +
#    project, then copy the project's public + secret keys into the env.
#    The Postgres volume persists across compose restarts, so this is a
#    one-time setup.
export LANGFUSE_HOST=http://localhost:3000
export LANGFUSE_PUBLIC_KEY=pk-lf-...
export LANGFUSE_SECRET_KEY=sk-lf-...

# 3. choose an LLM mode (see the table below) and run the pipeline.
#    Every node, every LLM call, every tool wrapper invocation is now
#    a span. record-missing is the recommended demo mode: one paid run
#    captures cassettes, every subsequent run replays them for free
#    while still emitting the trace.
RELEASELENS_LLM_MODE=record-missing \
  uv run releaselens run --pep-ids 658

# 4. refresh the Langfuse UI → Sessions, filter by the printed run_id.
#    LangGraph nodes appear as a trace tree; LLM generations under each
#    node carry input_tokens / output_tokens / cost_usd from LiteLLM;
#    test_author / critic spans carry the iteration attribute.
```

#### LLM modes (`RELEASELENS_LLM_MODE`)

| Mode | Behaviour | When to use |
|---|---|---|
| `replay` (default) | Refuses to call Bedrock; requires a cassette to exist for the exact prompt SHA, otherwise raises `CassetteMissing`. The `test_author` node converts that to a `budget_exhausted` terminal state per claim and the run completes with errors recorded in state. | Tests, deterministic CI. Will produce empty test-author / critic spans for any prompts that haven't been recorded — expected. |
| `record-missing` | Replay when a cassette exists; otherwise call Bedrock live and write the cassette. | Recommended for the trace demo: one run with AWS creds present captures every cassette, subsequent runs are free and identical. |
| `record` | Always call Bedrock live and overwrite the cassette. | Re-recording after a prompt change. |
| `live` | Always call Bedrock; never read or write cassettes. | Ad-hoc experimentation. |
| `stub` | Returns the canonical registered stub response per node. No Bedrock calls, no cassette I/O. | Smoke runs without AWS creds. Trace will show node spans but no real LLM generations. |

Default `replay` mode against a fresh PEP intentionally produces a noisy "trace full of `budget_exhausted`" — the cassettes under `tests/cassettes/` are sized to the unit tests, not to the real `pep_ingest` + `feature_extract` output, so prompt SHAs will not match. The graceful-degradation path is doing exactly what architecture §7.3.1 mandates; switch to `record-missing` once to capture the live cassettes.

[`docs/screenshots/langfuse-trace.png`](docs/screenshots/langfuse-trace.png, "Example Langfuse Trace")



`make langfuse-down` stops both containers; the named Postgres volume persists traces and your project keys between sessions, delete it explicitly (`docker volume rm releaselens-langfuse_langfuse_pg`) if you want a clean slate.

### 6. Lint and tests

```bash
make lint
make test
```

### 7. What does *not* work yet

```bash
uv run releaselens run --pep-ids 691,740   # FileNotFoundError — fixtures missing
uv run releaselens eval                     # prints stub message; no scoring
```

These are the natural next pieces of work — see the **Not done** list above.
