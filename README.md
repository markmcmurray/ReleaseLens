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

**Observability.** Langfuse tracing initialised at CLI entry (`observability/langfuse.py`).

**CLI.** `releaselens run | resume | eval` with click; `run` auto-copies the bundled PEP fixture into `data/peps/` if missing.

**Tests.** Unit tests for the loop nodes, RST parser, smoke tests, integration scaffolding; recorded LiteLLM cassettes under `tests/cassettes/`.

### Not done

The gap between scaffold-complete and architecture-complete is the [§19 done-state checklist](docs/architecture.md#19-done-state-checklist-for-the-implementer). The headline gaps:

- **Evidence nodes still produce stub records.** `evidence_static`, `evidence_changelog`, `evidence_probe` return deterministic `ImplementationEvidence` instances with `version_first_seen="0.0.0-stub"` rather than wiring the existing tool layer through. The tools exist; the nodes don't call them yet.
- **`DevpiPublicConnector` is synthetic.** Returns canned `ResolvedArtefact`s; no HTTP traffic to a real devpi.
- **Only PEP-658 has a fixture.** PEP-691 and PEP-740 are referenced by `make demo` but no RST is bundled. Running `--pep-ids 691,740` will fail at ingest.
- **Eval harness is a stub.** `eval/runner.py` and `eval/score.py` are placeholders; `data/fixtures/` is empty; `releaselens eval` short-circuits with a "no fixtures" message. Precision/recall/F1 against ground-truth is the next major chunk of work.
- **Langfuse self-host docker compose** is not committed; tracing initialises against whatever endpoint env vars point at.
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

### 5. Lint and tests

```bash
make lint
make test
```

### 6. What does *not* work yet

```bash
uv run releaselens run --pep-ids 691,740   # FileNotFoundError — fixtures missing
uv run releaselens eval                     # prints stub message; no scoring
```

These are the natural next pieces of work — see the **Not done** list above.
