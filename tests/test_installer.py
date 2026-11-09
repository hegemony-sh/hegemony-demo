# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""install.sh and compose.sh, driven as subprocesses against a fake `docker`.

Nothing here talks to a Docker daemon, pulls an image or uses the network:
the fake answers the few questions the preflight asks, and the clone tests
clone local repositories.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = [
    "awk", "base64", "basename", "bash", "cat", "chmod", "cut", "df", "dirname", "env",
    "git", "grep", "head", "id", "ls", "mkdir", "mv", "readlink", "rm", "sed", "sh", "stat",
    "tail", "touch", "tr", "uname", "curl",
]  # fmt: skip

FAKE_DOCKER = """#!/bin/sh
# Answers what install.sh asks; FAKE_* variables shape the answers.
case "$1" in
  info)
    [ "${FAKE_DOCKER_DOWN:-0}" = 1 ] && exit 1
    case "$*" in
      *MemTotal*) echo "${FAKE_MEMORY:-17179869184}" ;;
      *DockerRootDir*) echo "${FAKE_ROOT_DIR:-/}" ;;
    esac
    exit 0 ;;
  compose)
    [ "$2" = version ] && { echo "${FAKE_COMPOSE:-2.29.1}"; exit 0; }
    echo "docker $*" >> "${FAKE_LOG:-/dev/null}"
    exit 0 ;;
  ps) exit 0 ;;
esac
exit 0
"""

FAKE_DF = """#!/bin/sh
echo "Filesystem 1024-blocks Used Available Capacity Mounted on"
echo "fake 999999999 1 ${FAKE_FREE_KIB:-104857600} 1% /"
"""


@dataclass
class Sandbox:
    root: Path
    checkout: Path
    platform: Path
    bin: Path
    env: dict[str, str] = field(default_factory=dict)

    def run(
        self, *args: str, script: str = "install.sh", **env: str
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["sh", str(self.checkout / script), *args],
            cwd=self.root,
            env={**self.env, **env},
            capture_output=True,
            text=True,
            timeout=60,
        )


def _copy_checkout(dest: Path) -> None:
    for rel in ("install.sh", "platform.env", "spec/basic.yaml", "dist/demo.env"):
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dest / rel)
    shutil.copytree(
        ROOT / "deploy" / "compose",
        dest / "deploy" / "compose",
        ignore=shutil.ignore_patterns(".local", "plugin-wheels"),
    )


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "tag.gpgsign=false",
            *args,
        ],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def sandbox(tmp_path: Path) -> Iterator[Sandbox]:
    checkout = tmp_path / "work" / "demo"
    _copy_checkout(checkout)
    platform = tmp_path / "platform"
    (platform / "deploy" / "compose").mkdir(parents=True)
    (platform / "deploy" / "compose" / "docker-compose.prod.yml").write_text("services: {}\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in TOOLS:
        found = shutil.which(tool)
        if found:
            (bin_dir / tool).symlink_to(found)
    for name, script in (("docker", FAKE_DOCKER), ("df", FAKE_DF)):
        (bin_dir / name).unlink(missing_ok=True)
        (bin_dir / name).write_text(script)
        (bin_dir / name).chmod(0o755)
    env = {
        "PATH": str(bin_dir),
        "HOME": str(tmp_path / "home"),
        "HEGEMONY_PLATFORM_DIR": str(platform),
        "HEGEMONY_PLATFORM_VERSION": "1.0.0-rc.1",
        "FAKE_ROOT_DIR": str(tmp_path),
        "HEGEMONY_SKIP_RESOURCE_CHECKS": "0",
    }
    yield Sandbox(tmp_path, checkout, platform, bin_dir, env)


def _local_env(sandbox: Sandbox) -> dict[str, str]:
    path = sandbox.checkout / "deploy/compose/.local/demo.env"
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line and line[0] != "#"
    )


# ---------------------------------------------------------------- options


def test_help_names_every_token_variable(sandbox: Sandbox) -> None:
    result = sandbox.run("--help")
    assert result.returncode == 0
    for name in ("HEGEMONY_GIT_TOKEN", "HEGEMONY_GHCR_TOKEN", "HEGEMONY_GITHUB_TOKEN"):
        assert name in result.stdout


def test_version_is_main_until_stamped(sandbox: Sandbox) -> None:
    assert sandbox.run("--version").stdout.strip() == "main"


def test_an_unknown_option_is_refused(sandbox: Sandbox) -> None:
    result = sandbox.run("--bogus")
    assert result.returncode == 1
    assert "unknown option" in result.stderr


# -------------------------------------------------------------- preflight


def test_preflight_passes_on_a_good_machine(sandbox: Sandbox) -> None:
    result = sandbox.run("--preflight")
    assert result.returncode == 0, result.stderr
    assert "Preflight checks passed" in result.stdout
    assert not (sandbox.root / "hegemony-demo").exists(), "preflight must not create anything"


def test_preflight_needs_docker(sandbox: Sandbox) -> None:
    (sandbox.bin / "docker").unlink()
    result = sandbox.run("--preflight")
    assert result.returncode == 1
    assert "docker is required" in result.stderr


def test_preflight_needs_a_running_daemon(sandbox: Sandbox) -> None:
    result = sandbox.run("--preflight", FAKE_DOCKER_DOWN="1")
    assert result.returncode == 1
    assert "cannot talk to the Docker daemon" in result.stderr


@pytest.mark.parametrize("version", ["1.29.2", "2.20.3", "v2.23.0"])
def test_preflight_needs_compose_2_24(sandbox: Sandbox, version: str) -> None:
    result = sandbox.run("--preflight", FAKE_COMPOSE=version)
    assert result.returncode == 1
    assert "Compose 2.24 or newer" in result.stderr


def test_preflight_refuses_too_little_memory(sandbox: Sandbox) -> None:
    result = sandbox.run("--preflight", FAKE_MEMORY=str(4 * 2**30))
    assert result.returncode == 1
    assert "4 GiB of memory" in result.stderr


def test_preflight_warns_below_the_recommended_memory(sandbox: Sandbox) -> None:
    result = sandbox.run("--preflight", FAKE_MEMORY=str(7 * 2**30))
    assert result.returncode == 0
    assert "8 GiB is recommended" in result.stderr


def test_preflight_refuses_too_little_disk(sandbox: Sandbox) -> None:
    result = sandbox.run("--preflight", FAKE_FREE_KIB=str(10 * 2**20))
    assert result.returncode == 1
    assert "only 10 GiB free" in result.stderr


def test_resource_checks_can_be_skipped(sandbox: Sandbox) -> None:
    result = sandbox.run("--preflight", FAKE_MEMORY=str(2**30), HEGEMONY_SKIP_RESOURCE_CHECKS="1")
    assert result.returncode == 0
    assert "skipping the memory and disk checks" in result.stderr


# ------------------------------------------------------------ install path


def test_the_placeholder_pin_needs_a_version(sandbox: Sandbox) -> None:
    env = dict(sandbox.env)
    del env["HEGEMONY_PLATFORM_VERSION"]
    sandbox.env = env
    pin = (sandbox.checkout / "platform.env").read_text()
    if "HEGEMONY_PLATFORM_VERSION=placeholder-" not in pin:
        pytest.skip("platform.env pins a release")
    result = sandbox.run("--no-up")
    assert result.returncode == 1
    assert "pins no platform release yet" in result.stderr


def test_no_up_writes_a_private_password_and_does_not_print_it(sandbox: Sandbox) -> None:
    result = sandbox.run("--no-up")
    assert result.returncode == 0, result.stderr
    local = sandbox.checkout / "deploy/compose/.local/demo.env"
    assert stat.S_IMODE(local.stat().st_mode) == 0o600
    values = _local_env(sandbox)
    password = values["HEGEMONY_DEMO_PASSWORD"]
    assert len(password) == 24 and password.isalnum()
    assert len(values["KEYCLOAK_ADMIN_PASSWORD"]) == 24
    assert password != values["KEYCLOAK_ADMIN_PASSWORD"]
    key = values["HEGEMONY_REGISTRY_TOKEN_KEY"]
    assert len(key) == 64 and all(c in "0123456789abcdef" for c in key)
    assert key not in result.stdout + result.stderr
    assert values["HEGEMONY_PLATFORM_VERSION"] == "1.0.0-rc.1"
    assert values["HEGEMONY_PLATFORM_DIR"] == str(sandbox.platform)
    assert password not in result.stdout + result.stderr


def test_a_second_run_keeps_the_password(sandbox: Sandbox) -> None:
    assert sandbox.run("--no-up").returncode == 0
    first = _local_env(sandbox)
    assert sandbox.run("--no-up").returncode == 0
    again = _local_env(sandbox)
    assert again["HEGEMONY_DEMO_PASSWORD"] == first["HEGEMONY_DEMO_PASSWORD"]
    assert again["HEGEMONY_REGISTRY_TOKEN_KEY"] == first["HEGEMONY_REGISTRY_TOKEN_KEY"]


def test_a_chosen_password_is_used(sandbox: Sandbox) -> None:
    result = sandbox.run("--no-up", HEGEMONY_DEMO_PASSWORD="correct-horse-battery")
    assert result.returncode == 0, result.stderr
    assert _local_env(sandbox)["HEGEMONY_DEMO_PASSWORD"] == "correct-horse-battery"


@pytest.mark.parametrize(
    "password", ["short", "has space in it", "quote'in-the-middle", "$dollar-sign-x"]
)
def test_a_weak_or_unsafe_password_is_refused(sandbox: Sandbox, password: str) -> None:
    result = sandbox.run("--no-up", HEGEMONY_DEMO_PASSWORD=password)
    assert result.returncode == 1
    assert "HEGEMONY_DEMO_PASSWORD must be" in result.stderr


def test_tokens_never_reach_the_output(sandbox: Sandbox) -> None:
    token = "ghp_" + "x" * 36
    result = sandbox.run(
        "--no-up", HEGEMONY_GIT_TOKEN=token, HEGEMONY_GHCR_TOKEN=token, HEGEMONY_GITHUB_TOKEN=token
    )
    assert result.returncode == 0, result.stderr
    assert token not in result.stdout + result.stderr
    assert token not in (sandbox.checkout / "deploy/compose/.local/demo.env").read_text()


def _bare_repo(source: Path, dest: Path, tag: str | None = None) -> str:
    _git(source, "init", "-q", "-b", "main")
    _git(source, "add", "-A")
    _git(source, "commit", "-q", "-m", "init")
    if tag:
        _git(source, "tag", tag)
    _git(source.parent, "clone", "-q", "--bare", str(source), str(dest))
    return f"file://{dest}"


def test_piped_install_clones_the_demo_and_the_pinned_platform(sandbox: Sandbox) -> None:
    demo_url = _bare_repo(sandbox.checkout, sandbox.root / "demo.git")
    platform_url = _bare_repo(sandbox.platform, sandbox.root / "platform.git", "v1.0.0-rc.1")
    pin = sandbox.checkout / "platform.env"
    pin.write_text(
        pin.read_text().replace("https://github.com/hegemony-sh/hegemony.git", platform_url)
    )
    _git(sandbox.checkout, "commit", "-qam", "point the pin at the local platform")
    _git(sandbox.checkout, "push", "-q", str(sandbox.root / "demo.git"), "main")
    env = dict(sandbox.env)
    del env["HEGEMONY_PLATFORM_DIR"]
    script = (sandbox.checkout / "install.sh").read_text()
    result = subprocess.run(
        ["sh", "-s", "--", "--no-up", "--dir", "target"],
        input=script,
        cwd=sandbox.root,
        env={**env, "HEGEMONY_DEMO_REPO": demo_url, "HEGEMONY_DEMO_REF": "main"},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    target = sandbox.root / "target"
    assert (target / "demo" / "install.sh").is_file()
    assert (target / "platform" / ".hegemony-demo-clone").is_file()
    local = (target / "demo/deploy/compose/.local/demo.env").read_text()
    assert f"HEGEMONY_PLATFORM_DIR={target / 'platform'}" in local


def test_a_platform_directory_it_did_not_create_is_left_alone(sandbox: Sandbox) -> None:
    env = dict(sandbox.env)
    del env["HEGEMONY_PLATFORM_DIR"]
    sandbox.env = env
    foreign = sandbox.checkout.parent / "hegemony"
    foreign.mkdir()
    result = sandbox.run("--no-up")
    assert result.returncode == 1
    assert "was not created by this installer" in result.stderr


# ----------------------------------------------------------------- compose.sh


def _compose(sandbox: Sandbox, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(sandbox.checkout / "deploy/compose/compose.sh"), *args],
        env={**sandbox.env, "FAKE_LOG": str(sandbox.root / "docker.log"), **env},
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_compose_needs_the_install(sandbox: Sandbox) -> None:
    result = _compose(sandbox, "ps")
    assert result.returncode == 1
    assert "run install.sh" in result.stderr


def test_compose_layers_platform_then_demo_files(sandbox: Sandbox) -> None:
    assert sandbox.run("--no-up").returncode == 0
    result = _compose(sandbox, "ps")
    assert result.returncode == 0, result.stderr
    call = (sandbox.root / "docker.log").read_text().split()
    files = [call[i + 1] for i, arg in enumerate(call) if arg == "-f"]
    assert [Path(f).name for f in files] == [
        "docker-compose.prod.yml",
        "docker-compose.auth.yml",
        "docker-compose.s3.yml",
        "docker-compose.openbao-internal.yml",
        "docker-compose.dind.yml",
        "docker-compose.registry.yml",
        "docker-compose.demo.yml",
    ]
    env_files = [call[i + 1] for i, arg in enumerate(call) if arg == "--env-file"]
    assert [Path(f).name for f in env_files] == [".env.demo", "demo.env", "demo.env"]
    assert call[-1] == "ps"


def test_compose_gives_an_older_install_a_registry_token_key(sandbox: Sandbox) -> None:
    assert sandbox.run("--no-up").returncode == 0
    local = sandbox.checkout / "deploy/compose/.local/demo.env"
    local.write_text(
        "".join(
            line
            for line in local.read_text().splitlines(keepends=True)
            if not line.startswith("HEGEMONY_REGISTRY_TOKEN_KEY=")
        )
    )
    result = _compose(sandbox, "ps")
    assert result.returncode == 0, result.stderr
    key = _local_env(sandbox)["HEGEMONY_REGISTRY_TOKEN_KEY"]
    assert len(key) == 64
    assert key not in result.stdout + result.stderr
    assert stat.S_IMODE(local.stat().st_mode) == 0o600


def test_compose_refuses_the_placeholder(sandbox: Sandbox) -> None:
    assert sandbox.run("--no-up").returncode == 0
    local = sandbox.checkout / "deploy/compose/.local/demo.env"
    local.write_text(
        "\n".join(
            line
            for line in local.read_text().splitlines()
            if not line.startswith("HEGEMONY_PLATFORM_VERSION")
        )
        + "\n"
    )
    env = {k: v for k, v in sandbox.env.items() if k != "HEGEMONY_PLATFORM_VERSION"}
    sandbox.env = env
    if "placeholder-" not in (sandbox.checkout / "platform.env").read_text():
        pytest.skip("platform.env pins a release")
    result = _compose(sandbox, "ps")
    assert result.returncode == 1
    assert "pins no platform release yet" in result.stderr


@pytest.mark.skipif(
    not os.environ.get("HEGEMONY_TEST_PLATFORM_DIR"),
    reason="set HEGEMONY_TEST_PLATFORM_DIR to a platform checkout to render the full stack",
)
def test_the_full_stack_renders_against_a_platform_checkout(sandbox: Sandbox) -> None:
    real_docker = shutil.which("docker", path=os.environ.get("PATH"))
    assert real_docker
    (sandbox.bin / "docker").unlink()
    (sandbox.bin / "docker").symlink_to(real_docker)
    platform = os.environ["HEGEMONY_TEST_PLATFORM_DIR"]
    assert (
        sandbox.run(
            "--no-up", HEGEMONY_PLATFORM_DIR=platform, HEGEMONY_SKIP_RESOURCE_CHECKS="1"
        ).returncode
        == 0
    )
    result = _compose(sandbox, "config", "--quiet", HEGEMONY_PLATFORM_DIR=platform)
    assert result.returncode == 0, result.stderr
