#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Check that a tag may be released: `release_check.py v1.0.0+demo.2`.

A demo release is tagged after the platform release it runs: `v<platform>`,
or `v<platform>+demo.<n>` for a later demo-only fix. The pin in platform.env
must name that platform release (not the placeholder).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAG = re.compile(r"^v(?P<platform>\d+\.\d+\.\d+(?:-rc\.\d+)?)(?:\+demo\.(?P<n>[1-9]\d*))?$")


def pinned_version() -> str:
    for line in (ROOT / "platform.env").read_text().splitlines():
        if line.startswith("HEGEMONY_PLATFORM_VERSION="):
            return line.split("=", 1)[1].strip('"')
    return ""


def problems(tag: str) -> list[str]:
    found: list[str] = []
    match = TAG.match(tag)
    if not match:
        return [f"{tag!r} is not v<platform> or v<platform>+demo.<n>"]
    version = pinned_version()
    if version.startswith("placeholder-"):
        found.append(f"platform.env still holds the placeholder {version!r}")
    elif version != match.group("platform"):
        found.append(
            f"the tag names platform {match.group('platform')}, platform.env pins {version}"
        )
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    found = problems(argv[1])
    for problem in found:
        print(f"release_check: {problem}", file=sys.stderr)
    if not found:
        print(f"release_check: {argv[1]} may be released")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
