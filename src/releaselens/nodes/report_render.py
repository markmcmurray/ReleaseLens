"""report_render — Markdown templating from structured input (architecture.md §14)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TypedDict

from jinja2 import Environment, FileSystemLoader, select_autoescape

from releaselens.routing import get_model_for
from releaselens.schemas import (
    Feature,
    FeatureMatrix,
    FeatureMatrixRow,
    FeatureReport,
    ImpactFinding,
    ReportSummary,
    TargetRef,
    Tool,
    VerificationResult,
)

# Hardcoded for stable column order in the rendered matrix table.
_TOOL_COLUMNS: tuple[Tool, ...] = ("warehouse", "pip", "uv")


class _State(TypedDict, total=False):
    run_id: str
    pep_ids: list[str]
    target: TargetRef
    features: list[Feature]
    matrices: dict[str, FeatureMatrix]
    verifications: list[VerificationResult]
    impacts: list[ImpactFinding]


@dataclass(frozen=True)
class RenderedFeatureRow:
    feature: Feature | None
    row: FeatureMatrixRow
    verification: VerificationResult | None
    impact: ImpactFinding | None
    first_seen_tool: Tool | None
    first_seen_version: str | None
    temporal_gap_days: int | None


@dataclass(frozen=True)
class TimelineEntry:
    feature_id: str
    earliest_tool: Tool
    pep_finalised_on: date
    temporal_gap_days: int


@dataclass(frozen=True)
class RenderedPEPView:
    pep_id: str
    pep_status: str | None
    pep_finalised_on: date | None
    feature_rows: list[RenderedFeatureRow]
    timeline_entries: list[TimelineEntry]


_TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "templates"
_REPORTS_DIR = Path("reports")


def report_render(state: _State) -> dict:
    # run_id, pep_ids, target are graph-invocation inputs — required at this point.
    # Lists/dicts that fan-in producers may have left empty are read with .get default.
    run_id = state["run_id"]
    pep_ids = state["pep_ids"]
    target = state["target"]
    features = state.get("features", [])
    matrices = state.get("matrices", {})
    verifications = state.get("verifications", [])
    impacts = state.get("impacts", [])
    pep_ids_list = list(pep_ids)

    _ = get_model_for(__name__)
    template = _jinja_env().get_template("report.md.j2")

    pep_views = _build_pep_views(features, matrices, verifications, impacts)

    out_dir = _REPORTS_DIR / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "report.md"

    rendered = template.render(
        run_id=run_id,
        pep_ids=pep_ids_list,
        target=target,
        features=features,
        pep_views=pep_views,
        tool_columns=list(_TOOL_COLUMNS),
        verifications=verifications,
        impacts=impacts,
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


def _build_pep_views(
    features: list[Feature],
    matrices: dict[str, FeatureMatrix],
    verifications: list[VerificationResult],
    impacts: list[ImpactFinding],
) -> list[RenderedPEPView]:
    # Index once: O(features) lookups across the per-PEP loops.
    features_by_id: dict[str, Feature] = {f.id: f for f in features}
    verifications_by_feature: dict[str, VerificationResult] = {
        v.feature_id: v for v in verifications
    }
    impacts_by_feature: dict[str, ImpactFinding] = {i.feature_id: i for i in impacts}

    views: list[RenderedPEPView] = []
    for pep_id in sorted(matrices):
        matrix = matrices[pep_id]
        rendered_rows: list[RenderedFeatureRow] = []
        timeline: list[TimelineEntry] = []
        pep_status: str | None = None
        pep_finalised_on: date | None = None

        for row in sorted(matrix.rows, key=lambda r: r.feature_id):
            feature = features_by_id.get(row.feature_id)
            verification = verifications_by_feature.get(row.feature_id)
            impact = impacts_by_feature.get(row.feature_id)

            # PEP-level metadata: take from the first feature on this PEP that has it.
            if feature is not None:
                if pep_status is None:
                    pep_status = feature.pep_status
                if pep_finalised_on is None and feature.pep_finalised_on is not None:
                    pep_finalised_on = feature.pep_finalised_on

            first_seen_tool, first_seen_version = _resolve_first_seen(row, verification)
            temporal_gap = verification.temporal_gap_days if verification else None

            rendered_rows.append(
                RenderedFeatureRow(
                    feature=feature,
                    row=row,
                    verification=verification,
                    impact=impact,
                    first_seen_tool=first_seen_tool,
                    first_seen_version=first_seen_version,
                    temporal_gap_days=temporal_gap,
                )
            )

            if (
                feature is not None
                and feature.pep_finalised_on is not None
                and verification is not None
                and verification.earliest_tool is not None
                and verification.temporal_gap_days is not None
            ):
                timeline.append(
                    TimelineEntry(
                        feature_id=row.feature_id,
                        earliest_tool=verification.earliest_tool,
                        pep_finalised_on=feature.pep_finalised_on,
                        temporal_gap_days=verification.temporal_gap_days,
                    )
                )

        views.append(
            RenderedPEPView(
                pep_id=pep_id,
                pep_status=pep_status,
                pep_finalised_on=pep_finalised_on,
                feature_rows=rendered_rows,
                timeline_entries=timeline,
            )
        )

    return views


def _resolve_first_seen(
    row: FeatureMatrixRow, verification: VerificationResult | None
) -> tuple[Tool | None, str | None]:
    """Pick the (tool, version) pair to display in the 'First seen' column.

    Prefers verification.earliest_tool (it knows about release dates); falls back
    to the per_tool evidence with the lowest version string when verification is
    absent. Returns (None, None) when nothing was found anywhere.
    """
    if verification is not None and verification.earliest_tool is not None:
        ev = row.per_tool.get(verification.earliest_tool)
        return verification.earliest_tool, ev.version_first_seen if ev else None

    found_with_version: list[tuple[Tool, str]] = [
        (tool, ev.version_first_seen)
        for tool, ev in row.per_tool.items()
        if ev.found and ev.version_first_seen
    ]
    if not found_with_version:
        return None, None
    found_with_version.sort(key=lambda t: t[1])
    return found_with_version[0]


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
