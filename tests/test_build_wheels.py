# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""build-wheels.sh, driven as a subprocess against a fake `docker`.

A local platform build ships the SDK of the plugin checkouts beside it, so the
demo's plugin wheels have to be built from those checkouts too: a released
wheel pins the SDK of its own release and does not install on a newer one.
Nothing here talks to a Docker daemon or uses the network.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Records its arguments, then writes a wheel named after the mounted project's
# directory into the mounted /out, as `uv build --wheel` would.
FAKE_DOCKER = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$FAKE_LOG"
[ "${FAKE_FAIL:-0}" = 1 ] && exit 1
src= out=
while [ $# -gt 0 ]; do
  case "$1" in
    -v) case "$2" in
          *:/src:ro) src="${2%%:/src:ro}" ;;
          *:/out) out="${2%%:/out}" ;;
        esac
        shift 2 ;;
    *) shift ;;
  esac
done
name="$(basename "$src")"
touch "$out/hegemony_${name}-9.9.9-py3-none-any.whl"
"""


def _project(parent: Path, repo: str, kind: str, name: str, dist: str) -> None:
    project = parent / repo / kind / name
    project.mkdir(parents=True)
    (project / "pyproject.toml").write_text(f'[project]\nname = "{dist}"\nversion = "9.9.9"\n')


@pytest.fixture
def layout(tmp_path: Path) -> Path:
    """A demo checkout, and a platform checkout with its plugin repositories beside it."""
    demo = tmp_path / "demo"
    (demo / "deploy" / "compose").mkdir(parents=True)
    shutil.copy2(ROOT / "deploy" / "compose" / "build-wheels.sh", demo / "deploy" / "compose")
    (demo / "platform.env").write_text(
        "HEGEMONY_PLUGIN_WHEELS="
        f'"{"a" * 64}@https://github.com/hegemony-sh/hegemony-inventory-plugins/'
        'releases/download/v0.5.0/hegemony_inventory_git-0.5.0-py3-none-any.whl"\n'
    )
    work = tmp_path / "work"
    (work / "hegemony").mkdir(parents=True)
    inventory = "hegemony-inventory-plugins"
    _project(work, inventory, "plugins", "inventory_git", "hegemony-inventory-git")
    _project(work, inventory, "packages", "inventory_sdk", "hegemony-inventory-sdk")
    _project(work, "hegemony-step-plugins", "plugins", "steps_general", "hegemony-steps-general")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "docker"
    fake.write_text(FAKE_DOCKER)
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    return tmp_path


def _run(layout: Path, **env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(layout / "demo" / "deploy" / "compose" / "build-wheels.sh"),
            str(layout / "work" / "hegemony"),
            "ghcr.io/hegemony-sh/hegemony/api:local",
        ],
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": f"{layout / 'bin'}{os.pathsep}{os.environ['PATH']}",
            "FAKE_LOG": str(layout / "docker.log"),
            **env,
        },
    )


def _wheels(layout: Path) -> list[str]:
    out = layout / "demo" / "deploy" / "compose" / "plugin-wheels"
    return sorted(p.name for p in out.glob("*.whl"))


def test_builds_each_pinned_plugin_from_its_checkout(layout: Path) -> None:
    result = _run(layout)

    assert result.returncode == 0, result.stderr
    assert _wheels(layout) == ["hegemony_inventory_git-9.9.9-py3-none-any.whl"]
    (call,) = (layout / "docker.log").read_text().splitlines()
    source = layout / "work" / "hegemony-inventory-plugins" / "plugins" / "inventory_git"
    # In the platform image just built, as the calling user, source read-only.
    assert call.startswith("run --rm --pull never ")
    assert f"--user {os.getuid()}:{os.getgid()}" in call
    assert f"-v {source}:/src:ro" in call
    image = "ghcr.io/hegemony-sh/hegemony/api:local"
    assert f"{image} build --quiet --wheel --out-dir /out /src" in call


def test_replaces_wheels_left_by_an_earlier_bring_up(layout: Path) -> None:
    out = layout / "demo" / "deploy" / "compose" / "plugin-wheels"
    out.mkdir()
    (out / "hegemony_inventory_git-0.5.0-py3-none-any.whl").touch()

    result = _run(layout)

    assert result.returncode == 0, result.stderr
    assert _wheels(layout) == ["hegemony_inventory_git-9.9.9-py3-none-any.whl"]


def test_names_a_plugin_that_has_no_checkout(layout: Path) -> None:
    shutil.rmtree(layout / "work" / "hegemony-inventory-plugins" / "plugins" / "inventory_git")

    result = _run(layout)

    assert result.returncode != 0
    assert "expected one project named hegemony-inventory-git" in result.stderr
    assert not (layout / "docker.log").exists()


def test_a_failed_build_stops_the_bring_up(layout: Path) -> None:
    result = _run(layout, FAKE_FAIL="1")

    assert result.returncode != 0
    assert "building hegemony-inventory-git" in result.stderr
    assert _wheels(layout) == []
