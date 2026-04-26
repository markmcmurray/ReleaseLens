"""Tests for the RST section splitter."""

from __future__ import annotations

from releaselens.peps.rst import split_sections


def test_split_sections_extracts_top_level_headings() -> None:
    body = """\
PEP: 658
Title: Example


Abstract
========

The first section.


Specification
=============

The second section.
"""
    sections = split_sections(body)
    assert "Abstract" in sections
    assert "Specification" in sections
    assert sections["Abstract"].startswith("The first section.")
    assert sections["Specification"].startswith("The second section.")


def test_split_sections_preserves_preamble() -> None:
    body = """\
PEP: 658
Status: Final


Abstract
========

x
"""
    sections = split_sections(body)
    assert "preamble" in sections
    assert "Status: Final" in sections["preamble"]


def test_split_sections_keeps_subsections_inline() -> None:
    """Lines underlined with - or other non-= chars are subsection markers
    that should remain inline within their parent top-level section."""
    body = """\
Specification
=============

Subsection
----------

Subsection body.

Another Subsection
------------------

More body.
"""
    sections = split_sections(body)
    assert list(sections.keys()) == ["preamble", "Specification"]
    assert "Subsection" in sections["Specification"]
    assert "Another Subsection" in sections["Specification"]


def test_split_sections_real_pep_658() -> None:
    """Smoke test: the bundled PEP-658 fixture splits cleanly."""
    from pathlib import Path

    fixture = Path(__file__).parents[1] / "fixtures" / "peps" / "PEP-658.rst"
    sections = split_sections(fixture.read_text())
    expected = {"Abstract", "Motivation", "Rationale", "Specification", "References"}
    assert expected.issubset(sections.keys())
