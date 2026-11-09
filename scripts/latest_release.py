#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The newest published platform release, and the plugin wheels that go with it.

    latest_release.py show    print what the newest releases are
    latest_release.py write   pin them in platform.env
    latest_release.py check   fail when platform.env pins anything older

"Newest published" is the platform GitHub release published most recently,
release candidates included, drafts not. Publication time rather than version
order, because the repository still lists pre-launch releases with higher
numbers than the 1.0.0 candidates. The plugin wheels the demo
adds are not chosen separately: they come from the plugin releases that this
platform release was built with (its .github/plugin-pins.json), so the wheel
always matches the plugin SDK inside the images.

Standard library only, so a CI job can run it with the system python3. Reads
a token from HEGEMONY_GITHUB_TOKEN or GITHUB_TOKEN while the repositories are
private; it is sent only to api.github.com and never printed.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLATFORM_REPO = "hegemony-sh/hegemony"
INVENTORY_REPO = "hegemony-sh/hegemony-inventory-plugins"
# The wheels the demo adds on top of the images: (plugin repository, wheel name prefix).
WHEELS = ((INVENTORY_REPO, "hegemony_inventory_git-"),)
API = "https://api.github.com"
VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-rc\.(\d+))?$")


def pick_latest(releases: list[dict]) -> str:
    """The most recently published release, as X.Y.Z[-rc.N]."""
    candidates = [
        r
        for r in releases
        if not r.get("draft") and r.get("published_at") and VERSION.match(r.get("tag_name", ""))
    ]
    if not candidates:
        raise LookupError(f"{PLATFORM_REPO} has no published release")
    # ISO 8601 UTC timestamps from GitHub sort as text.
    return max(candidates, key=lambda r: r["published_at"])["tag_name"].removeprefix("v")


def wheel_pair(release: dict, prefix: str) -> str:
    """'<sha256>@<url>' for the one wheel in a release whose name starts with prefix."""
    assets = [a for a in release.get("assets", []) if a["name"].startswith(prefix)]
    assets = [a for a in assets if a["name"].endswith(".whl")]
    if len(assets) != 1:
        raise LookupError(
            f"{release.get('tag_name')}: expected one {prefix}*.whl, found {len(assets)}"
        )
    digest = assets[0].get("digest") or ""
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise LookupError(f"{assets[0]['name']}: GitHub reports no sha256 digest")
    return f"{digest.removeprefix('sha256:')}@{assets[0]['browser_download_url']}"


def render(text: str, version: str, wheels: str) -> str:
    """platform.env with the version and wheel lines replaced, everything else kept."""
    out = []
    for line in text.splitlines():
        if line.startswith("HEGEMONY_PLATFORM_VERSION="):
            line = f"HEGEMONY_PLATFORM_VERSION={version}"
        elif line.startswith("HEGEMONY_PLUGIN_WHEELS="):
            line = f'HEGEMONY_PLUGIN_WHEELS="{wheels}"'
        out.append(line)
    return "\n".join(out) + "\n"


def pinned(text: str) -> tuple[str, str]:
    values = {}
    for line in text.splitlines():
        key, _, value = line.partition("=")
        if key in ("HEGEMONY_PLATFORM_VERSION", "HEGEMONY_PLUGIN_WHEELS"):
            values[key] = value.strip('"')
    return values.get("HEGEMONY_PLATFORM_VERSION", ""), values.get("HEGEMONY_PLUGIN_WHEELS", "")


def _get(path: str, accept: str = "application/vnd.github+json") -> bytes:
    request = urllib.request.Request(f"{API}{path}", headers={"Accept": accept})  # noqa: S310
    token = os.environ.get("HEGEMONY_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - fixed https host
        return response.read()


def resolve() -> tuple[str, str]:
    """(platform version, HEGEMONY_PLUGIN_WHEELS value) for the newest platform release."""
    releases = json.loads(_get(f"/repos/{PLATFORM_REPO}/releases?per_page=100"))
    version = pick_latest(releases)
    pins = json.loads(
        _get(
            f"/repos/{PLATFORM_REPO}/contents/.github/plugin-pins.json?ref=v{version}",
            accept="application/vnd.github.raw+json",
        )
    )
    pairs = []
    for repo, prefix in WHEELS:
        ref = pins[repo.split("/", 1)[1]]["ref"]
        release = json.loads(_get(f"/repos/{repo}/releases/tags/{ref}"))
        pairs.append(wheel_pair(release, prefix))
    return version, " ".join(pairs)


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in ("show", "write", "check"):
        print(__doc__, file=sys.stderr)
        return 2
    env = ROOT / "platform.env"
    version, wheels = resolve()
    if argv[1] == "show":
        print(f"HEGEMONY_PLATFORM_VERSION={version}")
        print(f'HEGEMONY_PLUGIN_WHEELS="{wheels}"')
        return 0
    if argv[1] == "write":
        env.write_text(render(env.read_text(), version, wheels))
        print(f"latest_release: platform.env now pins platform {version}")
        return 0
    have_version, have_wheels = pinned(env.read_text())
    problems = []
    if have_version != version:
        problems.append(
            f"platform.env pins platform {have_version}, the newest release is {version}"
        )
    if have_wheels != wheels:
        problems.append(
            "platform.env pins other plugin wheels than that platform release was built with"
        )
    for problem in problems:
        print(f"latest_release: {problem}", file=sys.stderr)
    if problems:
        print("latest_release: run `python3 scripts/latest_release.py write`", file=sys.stderr)
        return 1
    print(f"latest_release: platform.env pins the newest releases (platform {version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
