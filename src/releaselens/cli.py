"""ReleaseLens CLI entry point (architecture.md §16, §13).

Subcommands:
- run    — execute the pipeline against a target
- resume — resume a checkpointed run by run_id
- eval   — score against ground-truth fixtures
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import click

from releaselens import __version__
from releaselens.observability.langfuse import (
    current_run_id,
    get_callback_handler,
    init_tracing,
)
from releaselens.schemas import TargetRef

_DATA_PEPS = Path("data/peps")
_FIXTURE_PEPS = Path("tests/fixtures/peps")


@click.group(help="ReleaseLens — PEP-driven Python packaging impact analysis.")
@click.version_option(__version__, prog_name="releaselens")
def main() -> None:
    init_tracing()


@main.command("run", help="Execute the pipeline against a target codebase.")
@click.option(
    "--pep-ids",
    default="691",
    show_default=True,
    help="Comma-separated PEP IDs (e.g. 658,691,740).",
)
@click.option(
    "--connector",
    default="devpi-public",
    show_default=True,
    help="Registry connector name.",
)
@click.option(
    "--package",
    default="stub-package",
    show_default=True,
    help="Target package name.",
)
@click.option(
    "--package-version",
    default=None,
    help="Target package version (omit for latest).",
)
def run_cmd(pep_ids: str, connector: str, package: str, package_version: str | None) -> None:
    from releaselens.graph import build_graph

    run_id = str(uuid.uuid4())
    pep_id_list = [_normalise_pep_id(p) for p in pep_ids.split(",") if p.strip()]
    _ensure_pep_files_on_disk(pep_id_list)
    target = TargetRef(connector=connector, package=package, version=package_version)

    current_run_id.set(run_id)
    callbacks = _trace_callbacks(run_id, pep_id_list, target)

    graph = build_graph()
    final_state = graph.invoke(
        {
            "run_id": run_id,
            "pep_ids": pep_id_list,
            "target": target,
            "confidence_threshold": 0.8,
            "test_retry_budget": 2,
            "test_acceptance_threshold": 0.75,
        },
        config={"configurable": {"thread_id": run_id}, "callbacks": callbacks},
    )

    report = final_state.get("report")
    if report is None:
        raise click.ClickException("Pipeline completed but no report was produced.")
    click.echo(f"run_id: {run_id}")
    click.echo(f"report: {report.markdown_path}")


@main.command("resume", help="Resume a checkpointed run by run_id.")
@click.argument("run_id")
def resume_cmd(run_id: str) -> None:
    from releaselens.graph import build_graph

    current_run_id.set(run_id)
    callbacks = _trace_callbacks(run_id, [], None)

    graph = build_graph()
    final_state = graph.invoke(
        None,
        config={"configurable": {"thread_id": run_id}, "callbacks": callbacks},
    )
    report = final_state.get("report") if final_state else None
    if report is None:
        raise click.ClickException(f"No completed report for run_id={run_id}.")
    click.echo(f"resumed run_id: {run_id}")
    click.echo(f"report: {report.markdown_path}")


@main.command("ingest-peps", help="Embed data/peps/*.rst into the local Chroma store.")
@click.option(
    "--peps-dir",
    default=str(_DATA_PEPS),
    show_default=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Directory of PEP .rst files to ingest.",
)
def ingest_peps_cmd(peps_dir: Path) -> None:
    from releaselens.tools.rag import RagStore

    paths = sorted(peps_dir.glob("*.rst"))
    if not paths:
        raise click.ClickException(f"No PEP .rst files found in {peps_dir}.")
    RagStore().ingest_peps(paths)
    click.echo(f"Ingested {len(paths)} PEP file(s) from {peps_dir}.")


@main.command("eval", help="Score the pipeline against ground-truth fixtures.")
@click.option("--runs", default=1, show_default=True, type=int)
@click.option(
    "--fixtures-dir",
    default="data/fixtures",
    show_default=True,
    type=click.Path(path_type=Path),
)
def eval_cmd(runs: int, fixtures_dir: Path) -> None:
    from releaselens.eval.runner import load_fixtures, run_eval

    if not fixtures_dir.exists() or not any(fixtures_dir.glob("PEP-*.yaml")):
        raise click.ClickException(f"No fixtures present at {fixtures_dir}/PEP-*.yaml.")

    fixtures = load_fixtures(fixtures_dir)
    pep_ids = [fx.pep_id for fx in fixtures]

    def _callbacks_for(run_id: str) -> list:
        # Tag eval traces per architecture §11.4 so they're filterable in Langfuse.
        current_run_id.set(run_id)
        return _trace_callbacks(run_id, pep_ids, None, extra_tags=["eval=true"])

    results = run_eval(fixtures_dir, runs=runs, callbacks_factory=_callbacks_for)
    _print_eval_summary(results)


def _print_eval_summary(results: list) -> None:
    if not results:
        click.echo("No eval runs produced.")
        return

    pep_ids = sorted(results[0].per_pep)

    click.echo(f"Runs: {len(results)}")
    for pep_id in pep_ids:
        feat_f1s = [r.per_pep[pep_id].feature_score.f1 for r in results]
        ev_f1s = [r.per_pep[pep_id].evidence_scores.aggregate.f1 for r in results]
        click.echo(f"\n{pep_id}")
        click.echo(f"  feature  F1: {_fmt_stat(feat_f1s)}")
        click.echo(f"  evidence F1 (aggregate): {_fmt_stat(ev_f1s)}")

        per_tool: dict[str, list[float]] = {}
        per_method: dict[str, list[float]] = {}
        for r in results:
            ev = r.per_pep[pep_id].evidence_scores
            for tool, s in ev.per_tool.items():
                per_tool.setdefault(tool, []).append(s.f1)
            for method, s in ev.per_method.items():
                per_method.setdefault(method, []).append(s.f1)
        for tool in sorted(per_tool):
            click.echo(f"    by tool   [{tool}]: {_fmt_stat(per_tool[tool])}")
        for method in sorted(per_method):
            click.echo(f"    by method [{method}]: {_fmt_stat(per_method[method])}")

    click.echo("\nrun ids: " + ", ".join(r.run_id for r in results))


def _fmt_stat(values: list[float]) -> str:
    from statistics import fmean, pstdev

    if len(values) == 1:
        return f"{values[0]:.3f}"
    return f"{fmean(values):.3f} ± {pstdev(values):.3f}"


def _trace_callbacks(
    run_id: str,
    pep_ids: list[str],
    target: TargetRef | None,
    *,
    extra_tags: list[str] | None = None,
) -> list:
    tags = [f"pep:{p}" for p in pep_ids]
    if target is not None:
        tags.append(f"target:{target.package}")
    if extra_tags:
        tags.extend(extra_tags)
    handler = get_callback_handler(run_id, tags=tags)
    return [handler] if handler is not None else []


def _normalise_pep_id(raw: str) -> str:
    raw = raw.strip()
    if raw.upper().startswith("PEP-"):
        return raw.upper()
    return f"PEP-{raw}"


def _ensure_pep_files_on_disk(pep_ids: list[str]) -> None:
    """Copy bundled fixture PEPs into data/peps if missing.

    Lets `releaselens run --pep-ids 658` work out of the box without manual
    setup: the fixture is the dev source of truth until a real fetcher lands.
    """
    _DATA_PEPS.mkdir(parents=True, exist_ok=True)
    for pep_id in pep_ids:
        target = _DATA_PEPS / f"{pep_id}.rst"
        if target.exists():
            continue
        fixture = _FIXTURE_PEPS / f"{pep_id}.rst"
        if fixture.exists():
            shutil.copyfile(fixture, target)
            click.echo(f"Copied fixture {fixture} -> {target}")


if __name__ == "__main__":
    main()
