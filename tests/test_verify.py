# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The post-install check fails loudly, and changes nothing, without a stack."""

from __future__ import annotations

import os
import pty
import shutil
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


def test_a_stopped_long_running_service_fails_the_check(tmp_path: Path) -> None:
    # migrate ran once and exited 0 (restart: "no"): fine. The worker also
    # exited 0, but it should keep running (restart: unless-stopped): a fail.
    demo = tmp_path / "demo"
    shutil.copytree(ROOT / "deploy", demo / "deploy")
    shutil.copy(ROOT / "platform.env", demo / "platform.env")
    (demo / "deploy/compose/.local").mkdir(parents=True, exist_ok=True)
    (demo / "deploy/compose/.local/demo.env").write_text("HEGEMONY_PLATFORM_VERSION=1.0.0\n")
    (tmp_path / "platform/deploy/compose").mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub(
        bin_dir,
        "docker",
        """case "$*" in
  *hegemony-lab*" ps "*) echo "gitea running healthy 0 lab1" ;;
  *" ps "*) printf 'api running healthy 0 c1\\nmigrate exited  0 c2\\nworker exited  0 c3\\n' ;;
  inspect*c2) echo no ;;
  inspect*) echo unless-stopped ;;
  *) exit 1 ;;
esac""",
    )
    _stub(bin_dir, "curl", "exit 7")
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HEGEMONY_LAB_CONVERGE_SECONDS": "1",
        "HEGEMONY_PLATFORM_DIR": str(tmp_path / "platform"),
    }
    result = subprocess.run(
        ["bash", str(demo / "deploy/compose/verify.sh")],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    services = next(
        line
        for line in result.stdout.splitlines()
        if line.startswith("[hegemony-demo] FAIL services")
    )
    assert "worker" in services, result.stdout
    assert "migrate" not in services, result.stdout
    assert "api" not in services, result.stdout


def test_verify_on_a_terminal_prints_checks_without_a_detail(tmp_path: Path) -> None:
    # On a terminal the checks are drawn with symbols; a check that passes
    # with no detail ("login server") must not trip `set -u`.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub(bin_dir, "docker", "exit 0")
    _stub(bin_dir, "curl", "exit 0")
    env: dict[str, str] = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "TERM": "xterm-256color",
        "LANG": "C.UTF-8",
        "HEGEMONY_LAB_CONVERGE_SECONDS": "1",
        "HEGEMONY_PLATFORM_DIR": str(tmp_path / "no-platform"),
    }
    env.pop("NO_COLOR", None)
    controller, terminal = pty.openpty()
    with subprocess.Popen(
        ["bash", str(ROOT / "deploy/compose/verify.sh")],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=terminal,
        stderr=terminal,
    ) as process:
        os.close(terminal)
        output = b""
        while True:
            try:
                chunk = os.read(controller, 4096)
            except OSError:
                break
            if not chunk:
                break
            output += chunk
        process.wait(timeout=120)
    os.close(controller)
    text = output.decode()
    assert "unbound variable" not in text, text
    assert "\033[32m✔\033[0m login server" in text, text
