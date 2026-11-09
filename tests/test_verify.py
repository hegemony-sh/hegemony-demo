# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The post-install check fails loudly, and changes nothing, without a stack."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _stub(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_verify_reports_each_failed_check_and_exits_1(tmp_path: Path) -> None:
    # No Docker daemon and nothing listening: every check must fail, and the
    # script must say so per check rather than stop at the first.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub(bin_dir, "docker", "exit 1")
    _stub(bin_dir, "curl", "exit 7")
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HEGEMONY_LAB_CONVERGE_SECONDS": "1",
        "HEGEMONY_PLATFORM_DIR": str(tmp_path / "no-platform"),
    }
    result = subprocess.run(
        ["bash", str(ROOT / "deploy/compose/verify.sh")],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    for check in ("services", "API ready", "lab network converged", "Gitea seeded",
                  "login server", "web UI", "mail sink"):  # fmt: skip
        assert any(line.startswith(f"[hegemony-demo] FAIL {check}") for line in lines), (
            check,
            result.stdout,
        )
    assert "check(s) failed" in result.stderr


def test_up_runs_the_check_before_the_banner() -> None:
    up = (ROOT / "deploy/compose/up.sh").read_text()
    assert up.index("verify.sh") < up.index("banner.sh")
