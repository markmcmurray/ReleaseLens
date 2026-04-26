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
from releaselens.observability.langfuse import init_tracing
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
        config={"configurable": {"thread_id": run_id}},
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

    graph = build_graph()
    final_state = graph.invoke(
        None,
        config={"configurable": {"thread_id": run_id}},
    )
    report = final_state.get("report") if final_state else None
    if report is None:
        raise click.ClickException(f"No completed report for run_id={run_id}.")
    click.echo(f"resumed run_id: {run_id}")
    click.echo(f"report: {report.markdown_path}")


@main.command("eval", help="Score the pipeline against ground-truth fixtures.")
@click.option("--runs", default=1, show_default=True, type=int)
def eval_cmd(runs: int) -> None:
    fixtures_dir = Path("data/fixtures")
    if not fixtures_dir.exists() or not any(fixtures_dir.glob("*.yaml")):
        click.echo("No fixtures present (data/fixtures/*.yaml). Eval is a stub in this scaffold.")
        return
    click.echo(f"Eval stub: would run {runs} run(s) against {fixtures_dir}.")


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
