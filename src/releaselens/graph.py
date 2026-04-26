"""LangGraph wiring (architecture.md §7.1).

All 12 nodes wired with Send fan-out at the 5 points listed in §7.2 and conditional
edges for the evidence escalation ladder (§7.3.2). The test-author/critic loop
(§7.3.1) is wired with a retry-budget conditional, although the stub critic always
accepts on iteration 0 so the loop is effectively single-shot in this scaffold.

Compiled with SqliteSaver checkpointer (architecture.md §13).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, get_args

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.types import Send

from releaselens.nodes.critic import critic
from releaselens.nodes.evidence_aggregate import evidence_aggregate
from releaselens.nodes.evidence_changelog import evidence_changelog
from releaselens.nodes.evidence_probe import evidence_probe
from releaselens.nodes.evidence_static import evidence_static
from releaselens.nodes.feature_extract import feature_extract
from releaselens.nodes.impact_scope import impact_scope
from releaselens.nodes.matrix_build import matrix_build
from releaselens.nodes.pep_ingest import pep_ingest
from releaselens.nodes.report_render import report_render
from releaselens.nodes.test_author import test_author
from releaselens.nodes.test_authoring_aggregate import test_authoring_aggregate
from releaselens.nodes.verify import verify
from releaselens.schemas import Tool
from releaselens.state import PipelineState

_TOOLS: tuple[Tool, ...] = get_args(Tool)
_DEFAULT_DB_PATH = Path(".releaselens/checkpoints.db")


# ---- Fan-out routers (architecture.md §7.2) -------------------------------------


def _fanout_pep_ingest(state: PipelineState) -> list[Send]:
    return [Send("pep_ingest", {"pep_id": pid}) for pid in state.get("pep_ids", [])]


def _fanout_feature_extract(state: PipelineState) -> list[Send]:
    sources = state.get("pep_sources", {})
    return [
        Send("feature_extract", {"pep_id": pid, "source": sources[pid]})
        for pid in state.get("pep_ids", [])
        if pid in sources
    ]


def _fanout_test_authoring(state: PipelineState) -> list[Send]:
    """Fan out one Send per spec claim across all features.

    Testable claims start the test-author/critic loop at iteration 0.
    Non-testable claims skip the loop entirely and go straight to the
    aggregator with status="unverifiable" — architecture §7.3.1 mandates
    this terminal state. The aggregator handles the empty case naturally
    (no shards, no results).
    """
    sends: list[Send] = []
    for feature in state.get("features", []):
        for claim in feature.spec_claims:
            if claim.testable:
                sends.append(
                    Send(
                        "test_author",
                        {
                            "claim_id": claim.id,
                            "claim_text": claim.claim_text,
                            "claim_type": claim.claim_type,
                            "pep_section_ref": claim.pep_section_ref,
                            "iteration": 0,
                        },
                    )
                )
            else:
                sends.append(
                    Send(
                        "test_authoring_aggregate",
                        {"claim_id": claim.id, "status": "unverifiable"},
                    )
                )
    return sends


def _fanout_evidence(state: PipelineState) -> list[Send]:
    sends: list[Send] = []
    for feature in state.get("features", []):
        for tool in _TOOLS:
            sends.append(Send("evidence_static", {"tool": tool, "feature": feature}))
    return sends


def _fanout_verify(state: PipelineState) -> list[Send]:
    return [
        Send(
            "verify",
            {
                "feature_id": f.id,
                "claim_ids": [c.id for c in f.spec_claims],
            },
        )
        for f in state.get("features", [])
    ]


def _fanout_impact(state: PipelineState) -> list[Send]:
    target = state.get("target")
    return [
        Send(
            "impact_scope",
            {"feature_id": f.id, "target": target},
        )
        for f in state.get("features", [])
    ]


# ---- Conditional edges (architecture.md §7.3) -----------------------------------


def _after_static(state: PipelineState) -> Send:
    return _escalate_or_aggregate(state, source_method="static", next_node="evidence_changelog")


def _after_changelog(state: PipelineState) -> Send:
    return _escalate_or_aggregate(state, source_method="changelog", next_node="evidence_probe")


def _escalate_or_aggregate(state: PipelineState, *, source_method: str, next_node: str) -> Send:
    """Route per-shard from an evidence node to its escalation target.

    String-returning conditional edges drop the Send payload that launched
    the source node, so downstream nodes lose (feature, tool) context. We
    rebuild the shard payload from the most recent evidence record of the
    source method — that record was just added by the shard whose routing
    we're computing. If confidence cleared the threshold, hand off to
    aggregate (state-driven, payload unused).
    """
    threshold = state.get("confidence_threshold", 0.8)
    latest = _latest_evidence_by_method(state, source_method)
    if latest is None or latest.confidence >= threshold:
        return Send("evidence_aggregate", {})
    feature = next(
        (f for f in state.get("features", []) if f.id == latest.feature_id),
        None,
    )
    return Send(next_node, {"feature": feature, "tool": latest.tool})


def _latest_evidence_by_method(state: PipelineState, method: str) -> Any:
    for ev in reversed(state.get("evidence", [])):
        if ev.method == method:
            return ev
    return None


# ---- No-op nodes used as join / dispatch points ---------------------------------


def _identity(_state: PipelineState) -> dict:
    return {}


# ---- Graph construction ---------------------------------------------------------


def build_graph(*, db_path: Path | None = None):
    """Build and compile the ReleaseLens graph with a SqliteSaver checkpointer."""
    g: StateGraph = StateGraph(PipelineState)

    # Nodes
    g.add_node("pep_ingest", pep_ingest)
    g.add_node("after_pep_ingest", _identity)
    g.add_node("feature_extract", feature_extract)
    g.add_node("after_feature_extract", _identity)
    g.add_node("test_author", test_author)
    g.add_node("critic", critic)
    g.add_node("test_authoring_aggregate", test_authoring_aggregate)
    g.add_node("after_test_authoring", _identity)
    g.add_node("evidence_static", evidence_static)
    g.add_node("evidence_changelog", evidence_changelog)
    g.add_node("evidence_probe", evidence_probe)
    g.add_node("evidence_aggregate", evidence_aggregate)
    g.add_node("matrix_build", matrix_build)
    g.add_node("verify", verify)
    g.add_node("impact_scope", impact_scope)
    g.add_node("report_render", report_render)

    # pep_ingest fan-out -> join -> feature_extract fan-out -> join.
    # Join nodes are necessary: conditional edges from a Send-fanned producer fire
    # per shard, which would re-fan-out N×N times. Joins barrier the graph so
    # downstream conditional edges fire once on the merged state.
    g.add_conditional_edges(START, _fanout_pep_ingest, ["pep_ingest"])
    g.add_edge("pep_ingest", "after_pep_ingest")
    g.add_conditional_edges("after_pep_ingest", _fanout_feature_extract, ["feature_extract"])
    g.add_edge("feature_extract", "after_feature_extract")

    # Test-author/critic loop (architecture.md §7.3.1, ADR-0007).
    # author and critic both return Command(goto=Send(...)) so the loop
    # iteration and terminal routing happen at node-level — no _fanout_critic
    # router is needed. Send targets must be declared in the conditional-edges
    # destination list so LangGraph knows the topology.
    g.add_conditional_edges(
        "after_feature_extract",
        _fanout_test_authoring,
        ["test_author", "test_authoring_aggregate"],
    )
    g.add_edge("test_authoring_aggregate", "after_test_authoring")

    # Evidence pipeline.
    g.add_conditional_edges("after_test_authoring", _fanout_evidence, ["evidence_static"])
    g.add_conditional_edges(
        "evidence_static",
        _after_static,
        ["evidence_changelog", "evidence_aggregate"],
    )
    g.add_conditional_edges(
        "evidence_changelog",
        _after_changelog,
        ["evidence_probe", "evidence_aggregate"],
    )
    g.add_edge("evidence_probe", "evidence_aggregate")

    # Tail. matrix_build is a single-instance node; verify/impact fan out per feature.
    g.add_edge("evidence_aggregate", "matrix_build")
    g.add_conditional_edges("matrix_build", _fanout_verify, ["verify"])
    g.add_conditional_edges("verify", _fanout_impact, ["impact_scope"])
    g.add_edge("impact_scope", "report_render")
    g.add_edge("report_render", END)

    db_path = db_path or _DEFAULT_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    saver = SqliteSaver(conn)
    return g.compile(checkpointer=saver)
