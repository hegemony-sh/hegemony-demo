# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""platform.env, the one platform pin, is well formed."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_pin() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (ROOT / "platform.env").read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        values[key] = value.strip('"')
    return values


def test_the_pin_names_a_version_or_the_placeholder() -> None:
    version = read_pin()["HEGEMONY_PLATFORM_VERSION"]
    assert re.fullmatch(r"placeholder-[0-9.]+(-rc)?|\d+\.\d+\.\d+(-rc\.\d+)?", version), version


def test_the_platform_version_is_pinned_only_in_platform_env() -> None:
    version = read_pin()["HEGEMONY_PLATFORM_VERSION"]
    hits = [
        p.relative_to(ROOT).as_posix()
        for p in ROOT.rglob("*")
        if p.is_file()
        and ".git" not in p.parts
        and ".venv" not in p.parts
        and p.suffix not in {".pyc", ".lock"}
        and p.name != "platform.env"
        and version in p.read_text(errors="ignore")
    ]
    assert hits == []


def test_every_plugin_wheel_is_https_and_sha256_pinned() -> None:
    pairs = read_pin()["HEGEMONY_PLUGIN_WHEELS"].split()
    assert pairs
    for pair in pairs:
        sha, _, url = pair.partition("@")
        assert re.fullmatch(r"[0-9a-f]{64}", sha), pair
        assert re.fullmatch(
            r"https://github\.com/hegemony-sh/[\w.-]+/releases/download/\S+\.whl", url
        )
