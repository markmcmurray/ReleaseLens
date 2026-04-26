"""Minimal RST section splitter for PEP documents.

PEPs use docutils-style underlined headings: a heading line followed by a row
of repeated punctuation characters of equal-or-greater length. We don't need
a full RST parser — we just need top-level sections (Abstract, Motivation,
Specification, etc.) keyed by their heading text. Subsection bodies remain
inline within the parent section, which is what feature_extract wants.

Headers underlined with ``=`` are treated as top-level. Other underline chars
(``-``, ``~``, ``"``, ``^``) belong to subsections and are kept inline.
"""

from __future__ import annotations

import re

_TOP_LEVEL_UNDERLINE = re.compile(r"^=+\s*$")


def split_sections(body: str) -> dict[str, str]:
    """Return {heading -> section_body} for top-level sections in an RST doc.

    Lines preceding the first top-level section are returned under the
    "preamble" key so PEP frontmatter (PEP/Title/Author/...) is preserved.
    """
    lines = body.splitlines()
    sections: dict[str, str] = {}
    current_heading = "preamble"
    current_buffer: list[str] = []

    i = 0
    while i < len(lines):
        line = lines[i]
        next_line = lines[i + 1] if i + 1 < len(lines) else ""

        if (
            line.strip()
            and _TOP_LEVEL_UNDERLINE.match(next_line)
            and len(next_line.strip()) >= len(line.strip())
        ):
            sections[current_heading] = "\n".join(current_buffer).strip()
            current_heading = line.strip()
            current_buffer = []
            i += 2
            continue

        current_buffer.append(line)
        i += 1

    sections[current_heading] = "\n".join(current_buffer).strip()
    return sections
