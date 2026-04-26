# AGENTS.md

## Scope of this document

AGENTS.md governs **how code is generated** in this repo. The artefact spec — what to build, schemas, graph topology, decisions — lives in `docs/architecture.md` and `docs/adr/`.

Before implementing, read the relevant section of `architecture.md`. Treat it as canonical for *what* the system does and *how it is shaped*; treat AGENTS.md as canonical for *how you generate code*.

Conflict-resolution rules:

- If `architecture.md` and existing code disagree, **flag the conflict and stop**. Do not silently align one to the other.
- If `architecture.md` is unclear at the point of implementation, the ambiguity is a bug in the doc — flag it and update the doc; do not guess.
- Substantive architectural decisions require an ADR in `docs/adr/`. Do not invent architectural decisions inline. If the spec is silent, propose an ADR or ask.

---

## Operating Mode

This repository is developed using LLM-assisted code generation under strict
determinism, testability, and minimal-diff constraints.

The LLM must behave as a conservative production engineer:
- Prefer explicitness over cleverness
- Prefer small, safe changes over large rewrites
- Never introduce hidden behaviour
- Treat all outputs as part of a deterministic pipeline

---

## System Context

For the system spec, see `docs/architecture.md`. AGENTS.md does not duplicate it.

The properties that code must preserve — schema-driven, multi-stage, evaluation-backed — are defined and enforced by that spec. If a generation choice would violate them, stop and flag.

---

## Global Invariants (Non-Negotiable)

- All logic must be testable via automated tests
- No silent failures
- No implicit state or side effects
- All data structures must be typed and validated
- No speculative or placeholder implementations
- No hidden coupling between pipeline stages
- All transformations must be reproducible

---

## Determinism Requirements

When generating code, default to deterministic constructs.

Required:
- Stable ordering of all collections
- No randomness without explicit seeding
- Canonicalisation of outputs (sorting, deduplication)
- Stable identifiers (the format is defined by `architecture.md`; do not invent UUIDs in its place)

Prohibited:
- Non-deterministic iteration
- Time-based logic in core pipeline
- Implicit reliance on external mutable state

Runtime determinism of the artefact (temperature pinning, model pin IDs, eval reproducibility) is specified in `architecture.md`. Follow it; do not relax it.

---

## Change Policy

When modifying code, the LLM must:

1. Minimise diff size
   - Do not refactor unrelated code
   - Do not rename symbols unless necessary

2. Preserve behaviour
   - Unless explicitly instructed otherwise
   - Behaviour changes must be covered by tests

3. Maintain compatibility
   - Avoid breaking existing interfaces

4. Justify structural changes
   - New modules require clear necessity

---

## Diff Discipline

Preferred order of operations:

1. Modify existing code
2. Extend existing modules
3. Introduce new modules only if required

Avoid:
- Large rewrites
- Cross-cutting refactors
- Mixing refactor + feature changes in one step

---

## Code Standards

### General

- Use explicit typing (no implicit `Any`)
- Prefer pure functions
- Avoid global mutable state
- Keep functions small and composable
- Avoid unnecessary abstraction

### Error Handling

- Fail fast on invalid input
- Use explicit exceptions
- Do not swallow errors
- Do not use broad `except`

**Inside graph nodes**, distinguish two failure modes:

- **Programmer error** (KeyError on a guaranteed shard field, schema mismatch from a co-developed node, type errors): raise. The graph should crash, the test should fail loudly, the cause is a code bug.
- **Contract failure** (LLM returned malformed JSON, Bedrock 5xx, disk read failed, cassette missing in replay mode): catch the specific exception, return `{"errors": [ErrorRecord(...)]}` with `severity="error"` and a specific message. Architecture.md §7.4 mandates that degraded runs still produce a partial report — raising here breaks that. The whole pipeline must remain capable of completing even when individual nodes fail their contracts.

---

## Schema Discipline

Follow the schemas and validation boundaries defined in `architecture.md` §3–§4. Do not introduce new inter-stage types without updating that section.

Behavioural rules (these stay here, not in the spec):

- Never bypass schema validation at a boundary, even temporarily.
- LLM outputs are not trusted until (1) schema validation passes and (2) canonicalisation is applied.
- Prefer omission over fabrication: if a field can't be filled honestly, leave it unset rather than inventing a value.

---

## LangGraph Structure Rules

Graph topology, node contracts, fan-out points, and reducer rules are specified in `architecture.md` §3 and §7. Follow them.

Behavioural rules:

- Each node lives in its own module under `src/releaselens/nodes/`.
- Each node behaves like a pure function over its input state slice — no hidden state, no implicit cross-node coupling.
- No circular dependencies. Shared types stay centralised under `src/releaselens/schemas/`.
- Do not invent new fan-out mechanisms or parallelism primitives; use what the spec prescribes.

---

## LLM Guardrails

The LLM must NOT:

- Invent APIs or functions not present in the codebase
- Assume behaviour without verifying in code
- Introduce placeholder implementations without marking clearly
- Generate TODOs unless explicitly requested
- Perform implicit joins or hidden reasoning across stages

The LLM must:

- Read existing code before modifying it
- Reuse existing abstractions where appropriate
- Prefer omission over fabrication
- Explicitly link related entities via IDs

---

## LLM Call Discipline

These rules govern code-gen for any node that calls a language model. The cassette infrastructure and stub registry are specified in `architecture.md` §11.6.1 and §6 — follow them exactly; deviation breaks test determinism in ways that surface only in CI.

1. **All LLM calls go through `releaselens.llm.call(node_name, system=..., user=...)`.** Never import `litellm` or any provider SDK directly inside a node. The wrapper is the seam that makes cassettes work; bypassing it bypasses tests and produces flakes that take hours to diagnose.

2. **Every LLM-bearing node registers a deterministic stub at module load** via `llm.register_stub(node_name, response_json)`. The stub must produce a response that the node's downstream parser accepts so the smoke test can run the full graph under `RELEASELENS_LLM_MODE=stub` without cassettes or Bedrock creds. A node that calls the LLM but doesn't register a stub is a broken node.

3. **JSON-out LLM nodes follow this template:** prompt the model for strict JSON only, strip ```json fences if the model wraps them, validate the response against a private Pydantic extraction model, then map to the public schema with deterministic IDs. Never `json.loads` straight into the public schema — the extraction-model step is what makes prompt drift visible as a clean validation error rather than a mysterious AttributeError downstream.

4. **Stable IDs follow the rule in `architecture.md` §4.1 / §4.2** — `<pep_id_lower>.<slug-of-title>` for features, `<feature_id>.claim-NN` for claims (1-based source-order index). Never use UUIDs, never include random or time-based bits. Eval set arithmetic (§11.3) depends on the same input always producing the same IDs.

5. **Cassette modes are not interchangeable.** Default tests run in `replay`. Recording is `record-missing`, used once locally with Bedrock creds. CI never records. A test that calls the LLM must skip-with-instruction (not silently call live) when `replay` mode is active and the cassette is absent.

---

## Closed World Assumption

Operate only on inputs defined in `architecture.md`.

The LLM must NOT:
- Use external knowledge of packages, tools, or PEPs beyond what the inputs provide
- Infer undocumented behaviour
- Fill gaps with assumptions

If an input the spec implies should exist isn't present, that's a bug — flag it.

---

## No Compression Rule

Do not summarise or merge distinct items.

- Spec claims must remain atomic (one assertion per `SpecClaim`)
- Evidence records must remain atomic (one per feature × tool × method)
- Tests must target a single behaviour

---

## Testing Requirements

All non-trivial changes must include:

- Unit tests for core logic
- Edge case coverage
- Deterministic assertions

Tests must:

- Validate observable behaviour only
- Avoid over-mocking
- Be minimal and focused
- Avoid timing-based assertions

---

## Evaluator Loop Constraints

The test-author/critic loop semantics — retry budget, acceptance threshold, feedback piping, terminal states — are specified in `architecture.md` §7.3.1 and ADR-0007. Do not deviate.

Behavioural rules at code-gen time:

- Do not soften the loop's terminal states (`accepted` / `budget_exhausted` / `unverifiable`) into a single "best effort" output.
- Flaky or non-deterministic tests must be rejected by the critic, not papered over.
- The critic's `feedback` field must be threaded into the next author iteration's prompt — without that, the loop is a sham.

---

## Tool Usage Rules

Tools must be treated as strict contracts.

The LLM must:
- Follow defined input/output schemas exactly
- Handle failure states explicitly
- Never reinterpret tool outputs

---

## Observability

Span hierarchy and required span attributes are specified in `architecture.md` §10.2–§10.3. Do not add or remove span fields without updating that section.

Behavioural rules:

- All critical paths include structured logging keyed by stable identifiers (e.g. `claim_id`, `feature_id`, `run_id`).
- Avoid excessive verbosity; logs exist to support drill-down debugging, not as a narrative.

---

## Two-Pass Rule

For non-trivial changes:

Pass 1:
- Implement minimal logic to satisfy requirement

Pass 2:
- Add tests
- Validate invariants
- Ensure determinism

Do not combine both into a single large change.

---

## Uncertainty Handling

If requirements are unclear, the LLM must:

1. Ask for clarification, OR
2. Implement the smallest reasonable interpretation

Never:
- Assume hidden requirements
- Over-engineer speculative solutions

---

## Anti-Overengineering Rule

Do not:
- Generalise beyond current requirements
- Introduce abstractions for hypothetical reuse

Do:
- Solve the specific problem directly
- Optimise for clarity and traceability

---

## Failure Handling

If a task cannot be completed safely:

- Fail explicitly
- Provide reason
- Do not produce partial or speculative outputs

---

## Definition of Done

A change is complete only if:

- Code compiles and runs
- Tests pass
- Schemas are enforced
- Behaviour is deterministic
- No invariants are violated

---

## Guiding Principle

Treat the LLM as a non-deterministic compiler pass that must be constrained by:
- schemas
- invariants
- tests
- explicit contracts

All code must reinforce these constraints.