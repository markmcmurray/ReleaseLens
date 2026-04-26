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
    # run_id, pep_ids, target are graph-invocation inputs — required at this point.
    # Lists/dicts that fan-in producers may have left empty are read with .get default.
    run_id = state["run_id"]
    pep_ids = state["pep_ids"]
    target = state["target"]
    features = state.get("features", [])
    pep_ids_list = list(pep_ids)

    _ = get_model_for(__name__)
    template = _jinja_env().get_template("report.md.j2")

    out_dir = _REPORTS_DIR / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "report.md"

    rendered = template.render(
        run_id=run_id,
        pep_ids=pep_ids_list,
        target=target,
        features=features,
        matrices=state.get("matrices", {}),
        verifications=state.get("verifications", []),
        impacts=state.get("impacts", []),
    )
    out_path.write_text(rendered)

    report = FeatureReport(
        run_id=run_id,
        pep_ids=pep_ids_list,
        target=target,
        markdown_path=out_path,
        summary=ReportSummary(feature_count=len(features), pep_count=len(pep_ids_list)),
        generated_at=datetime.now(UTC),
    )
    return {"report": report}


def _jinja_env() -> Environment:
    global _ENV
    if _ENV is None:
        _ENV = Environment(
            loader=FileSystemLoader(_TEMPLATES_DIR),
            autoescape=select_autoescape(),
            keep_trailing_newline=True,
        )
    return _ENV


_ENV: Environment | None = None
