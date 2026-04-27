"""CLI smoke test for `releaselens eval`."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from click.testing import CliRunner

from releaselens.cli import main


_FIXTURE_YAML = dedent("""
    pep_id: PEP-658
    pep_finalised_on: 2021-05-25
    features:
      - id: pep-658.metadata-sidecar
        title: Serve distribution metadata as a sidecar file
        spec_claims:
          - id: pep-658.metadata-sidecar.claim-01
            claim_text: "data-dist-info-metadata attribute"
        expected_evidence:
          pip:
            found: true
            version_first_seen: "22.3"
""").lstrip()


def test_eval_command_runs_against_fixture(tmp_path: Path) -> None:
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    (fixtures_dir / "PEP-658.yaml").write_text(_FIXTURE_YAML)

    result = CliRunner().invoke(
        main,
        ["eval", "--runs", "1", "--fixtures-dir", str(fixtures_dir)],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    assert "PEP-658" in result.output
    assert "feature  F1:" in result.output
    assert "evidence F1 (aggregate):" in result.output


def test_eval_command_errors_when_no_fixtures(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    result = CliRunner().invoke(
        main, ["eval", "--fixtures-dir", str(empty)], catch_exceptions=False
    )
    assert result.exit_code != 0
    assert "No fixtures present" in result.output
