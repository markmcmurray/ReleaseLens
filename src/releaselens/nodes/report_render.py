"""report_render — Markdown templating from structured input (architecture.md §14)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

from jinja2 import Environment, FileSystemLoader, select_autoescape

from releaselens.routing import get_model_for
from releaselens.schemas import (
    Feature,
    FeatureMatrix,
    FeatureReport,
    ImpactFinding,
    ReportSummary,
    TargetRef,
    VerificationResult,
)


class _State(TypedDict, total=False):
    run_id: str
    pep_ids: list[str]
    target: TargetRef
    features: list[Feature]
    matrices: dict[str, FeatureMatrix]
    verifications: list[VerificationResult]
    impacts: list[ImpactFinding]


_TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "templates"
_REPORTS_DIR = Path("reports")


def report_render(state: _State) -> dict:
    _ = get_model_for(__name__)
    env = Environment(
        loader=FileSystemLoader(_TEMPLATES_DIR),
        autoescape=select_autoescape(),
        keep_trailing_newline=True,
    )
    template = env.get_template("report.md.j2")

    run_id = state.get("run_id", "unknown-run")
    out_dir = _REPORTS_DIR / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "report.md"

    rendered = template.render(
        run_id=run_id,
        pep_ids=state.get("pep_ids", []),
        target=state.get("target"),
        features=state.get("features", []),
        matrices=state.get("matrices", {}),
        verifications=state.get("verifications", []),
        impacts=state.get("impacts", []),
    )
    out_path.write_text(rendered)

    summary = ReportSummary(
        feature_count=len(state.get("features", [])),
        pep_count=len(state.get("pep_ids", [])),
    )
    report = FeatureReport(
        run_id=run_id,
        pep_ids=state.get("pep_ids", []),
        target=state.get("target") or TargetRef(connector="stub", package="stub"),
        markdown_path=out_path,
        summary=summary,
        generated_at=datetime.now(UTC),
    )
    return {"report": report}
