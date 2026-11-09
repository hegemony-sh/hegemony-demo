# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The lab's inventory: the pin, the fetch, and the check against the spec."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import yaml
from hegemony_demo_gen.cli import main as demo_gen
from hegemony_demo_gen.model import Model, build_model
from hegemony_demo_gen.render import check_inventory, dump_yaml, inventory_documents
from hegemony_demo_gen.spec import load_spec

from tests.test_platform_pin import read_pin

ROOT = Path(__file__).resolve().parents[1]
FETCH = ROOT / "deploy" / "lab" / "fetch-inventory.sh"


def _model() -> Model:
    return build_model(load_spec(ROOT / "spec" / "basic.yaml"))


def _write_expected(tree: Path) -> None:
    """The tree the spec expects, each record with a comment of its own."""
    for path, document in inventory_documents(_model()).items():
        target = tree / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("" if document is None else "# a comment\n" + dump_yaml(document))


def test_the_pin_names_a_release_tag_of_the_inventory_repository() -> None:
    pin = read_pin()
    assert pin["HEGEMONY_INVENTORY_REPO"] == (
        "https://github.com/hegemony-sh/hegemony-demo-inventory.git"
    )
    assert re.fullmatch(r"v\d{4}\.\d{2}\.\d{2}", pin["HEGEMONY_INVENTORY_REF"])


def test_a_matching_tree_passes_whatever_its_comments(tmp_path: Path) -> None:
    _write_expected(tmp_path)
    assert check_inventory(_model(), tmp_path) == []
    assert demo_gen(["--root", str(ROOT), "--check-inventory", str(tmp_path)]) == 0


def test_a_drifted_tree_names_every_difference(tmp_path: Path) -> None:
    _write_expected(tmp_path)
    device = next((tmp_path / "devices").glob("*.yaml"))
    record = yaml.safe_load(device.read_text())
    record["mgmt_host"] = "192.0.2.1"
    device.write_text(dump_yaml(record))
    site = next((tmp_path / "sites").rglob("*.yaml"))
    site.unlink()
    (tmp_path / "devices" / "stray.yaml").write_text("schema_version: 1\n")
    problems = check_inventory(_model(), tmp_path)
    assert f"differs: devices/{device.name}" in problems
    assert f"missing: {site.relative_to(tmp_path).as_posix()}" in problems
    assert "extra:   devices/stray.yaml" in problems
    assert demo_gen(["--root", str(ROOT), "--check-inventory", str(tmp_path)]) == 1


def test_a_missing_tree_fails(tmp_path: Path) -> None:
    assert check_inventory(_model(), tmp_path / "nowhere") == [f"missing: {tmp_path / 'nowhere'}"]


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def _inventory_repo(tmp_path: Path, tree: bool = True) -> Path:
    """A local hegemony-demo-inventory stand-in, tagged v2000.01.01."""
    repo = tmp_path / "inventory-repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    if tree:
        _write_expected(repo / "inventory")
    else:
        (repo / "README.md").write_text("no inventory\n")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "x")
    _git(repo, "tag", "v2000.01.01")
    return repo


def _fetch(tmp_path: Path, repo: Path) -> subprocess.CompletedProcess[str]:
    """fetch-inventory.sh, in a copy of the demo, pointed at a local repository."""
    lab = tmp_path / "demo" / "deploy" / "lab"
    lab.mkdir(parents=True, exist_ok=True)
    (lab / FETCH.name).write_text(FETCH.read_text())
    (tmp_path / "demo" / "platform.env").write_text((ROOT / "platform.env").read_text())
    env = {
        **os.environ,
        "HEGEMONY_INVENTORY_REPO": f"file://{repo}",
        "HEGEMONY_INVENTORY_REF": "v2000.01.01",
    }
    return subprocess.run(
        ["bash", str(lab / FETCH.name)], env=env, capture_output=True, text=True, check=False
    )


def test_fetch_copies_the_tagged_tree_where_the_seed_reads_it(tmp_path: Path) -> None:
    repo = _inventory_repo(tmp_path)
    result = _fetch(tmp_path, repo)
    assert result.returncode == 0, result.stderr
    assert "downloading" in result.stdout
    fetched = tmp_path / "demo" / "deploy" / "lab" / "inventory"
    assert check_inventory(_model(), fetched) == []
    again = _fetch(tmp_path, repo)
    assert again.returncode == 0, again.stderr
    assert "present" in again.stdout


def test_fetch_refuses_a_tag_without_an_inventory(tmp_path: Path) -> None:
    result = _fetch(tmp_path, _inventory_repo(tmp_path, tree=False))
    assert result.returncode != 0
    assert "has no inventory/sites/" in result.stderr


def test_the_lab_seeds_gitea_from_the_fetched_tree() -> None:
    compose = yaml.safe_load((ROOT / "dist" / "lab" / "compose.yml").read_text())
    volumes = compose["services"]["gitea-seed"]["volumes"]
    assert "../../deploy/lab/inventory:/seed/inventory:ro" in volumes
    ignored = (ROOT / ".gitignore").read_text().splitlines()
    assert {"deploy/lab/inventory/", "deploy/lab/inventory.ref"} <= set(ignored)
    assert '"$lab_dir/fetch-inventory.sh"' in (ROOT / "deploy" / "lab" / "up.sh").read_text()
