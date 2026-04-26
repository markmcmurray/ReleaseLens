"""End-to-end smoke tests for the scaffold (Block 2.1 done-state)."""

from __future__ import annotations

from pathlib import Path

import pytest

from releaselens.schemas import TargetRef


def test_package_imports() -> None:
    import releaselens

    assert releaselens.__version__


def test_graph_compiles(tmp_path: Path) -> None:
    from releaselens.graph import build_graph

    graph = build_graph(db_path=tmp_path / "checkpoints.db")
    assert graph is not None


def test_end_to_end_stub_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    from releaselens.graph import build_graph

    graph = build_graph(db_path=tmp_path / "checkpoints.db")
    target = TargetRef(connector="devpi-public", package="stub-package", version=None)

    final_state = graph.invoke(
        {
            "run_id": "test-run-001",
            "pep_ids": ["PEP-691"],
            "target": target,
            "confidence_threshold": 0.8,
            "test_retry_budget": 2,
            "test_acceptance_threshold": 0.75,
        },
        config={"configurable": {"thread_id": "test-run-001"}},
    )

    report = final_state.get("report")
    assert report is not None
    assert report.markdown_path.exists()
    contents = report.markdown_path.read_text()
    assert "ReleaseLens Report" in contents
    assert "test-run-001" in contents
