# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The docs agree with the data and their links resolve."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = sorted(
    p
    for p in [*ROOT.glob("*.md"), *(ROOT / "docs").rglob("*.md"), *(ROOT / "stories").rglob("*.md")]
)
LINK = re.compile(r"\]\(([^)#\s]+)(#[^)\s]*)?\)")


def test_readme_numbers_match_the_generated_data() -> None:
    summary = json.loads((ROOT / "dist" / "summary.json").read_text())
    readme = (ROOT / "README.md").read_text()
    expected = (
        f"{summary['organizations']} organizations, {summary['users']} users, "
        f"{summary['sites']} sites and {summary['devices']}\ndevices. "
        f"Its lab runs {summary['lab_routers']} routers (one of them the upstream provider)\n"
        f"and {summary['lab_servers']} servers"
    )
    assert expected in readme


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_relative_links_resolve(doc: Path) -> None:
    for target, _anchor in LINK.findall(doc.read_text()):
        if re.match(r"[a-z]+:", target):
            continue
        assert (doc.parent / target).exists(), f"{doc.name}: {target}"


def test_every_story_is_in_the_walkthrough() -> None:
    walkthrough = (ROOT / "docs" / "walkthrough.md").read_text()
    for flow in ("Announce service prefix", "Maintenance window", "Standards check"):
        assert flow in walkthrough
