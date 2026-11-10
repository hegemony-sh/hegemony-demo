# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Every third-party action is pinned to a full commit SHA."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
USES = re.compile(r"^\s*-?\s*uses:\s*(\S+)(.*)$")


def test_there_are_workflows() -> None:
    assert WORKFLOWS


def test_every_action_is_pinned_to_a_commit_sha() -> None:
    unpinned: list[str] = []
    for workflow in WORKFLOWS:
        for number, line in enumerate(workflow.read_text().splitlines(), start=1):
            match = USES.match(line)
            if not match or match.group(1).startswith("./"):
                continue
            ref = match.group(1).partition("@")[2]
            if not re.fullmatch(r"[0-9a-f]{40}", ref) or "#" not in match.group(2):
                unpinned.append(f"{workflow.name}:{number}: {line.strip()}")
    assert not unpinned, "pin actions to a SHA with a version comment:\n" + "\n".join(unpinned)


def test_workflows_default_to_read_only_permissions() -> None:
    for workflow in WORKFLOWS:
        permissions = yaml.safe_load(workflow.read_text()).get("permissions")
        assert permissions in ({}, {"contents": "read"}), workflow.name
