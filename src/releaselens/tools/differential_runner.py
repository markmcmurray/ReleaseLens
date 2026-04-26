"""Differential test runner (architecture.md §9, ADR-0005).

Executes DifferentialTests produced by the test-author/critic loop. Three executors
keyed on test_kind:
- static_signature  -> ripgrep + importlib/inspect resolution
- behavioural_probe -> invokes pip / uv against a controlled fixture index in a uv venv
- metadata_assertion -> HTTP GET against the registry, JSON path assertion

NO LLM in this path (ADR-0005). The runner produces hard pass/fail/error signals;
LLMs only interpret those signals downstream when assigning confidence.

Implementation deferred to a later block.
"""
