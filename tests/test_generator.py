# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The generator: deterministic, current, `extends`, and its spec checks."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml
from hegemony_demo_gen.cli import check, generate, main
from hegemony_demo_gen.model import build_model, serial_for, stable_uuid
from hegemony_demo_gen.spec import SpecError, load_spec, merge

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "spec" / "basic.yaml"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_two_runs_give_the_same_bytes() -> None:
    assert generate(ROOT, SPEC) == generate(ROOT, SPEC)


def test_committed_output_is_current() -> None:
    assert check(ROOT, generate(ROOT, SPEC)) == []


def test_check_reports_a_changed_a_missing_and_a_stale_file(tmp_path: Path) -> None:
    files = {"dist/a.txt": "a\n", "dist/b.txt": "b\n"}
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "a.txt").write_text("changed\n")
    (tmp_path / "dist" / "old.txt").write_text("old\n")
    assert check(tmp_path, files) == [
        "differs: dist/a.txt",
        "missing: dist/b.txt",
        "stale:   dist/old.txt",
    ]


def test_main_check_fails_on_a_stale_tree(tmp_path: Path) -> None:
    (tmp_path / "spec").mkdir()
    (tmp_path / "spec" / "basic.yaml").write_text((FIXTURES / "tiny.yaml").read_text())
    assert main(["--root", str(tmp_path), "--check"]) == 1
    assert main(["--root", str(tmp_path)]) == 0
    assert main(["--root", str(tmp_path), "--check"]) == 0


def test_ids_and_serials_are_stable_and_synthetic() -> None:
    assert stable_uuid("user", "noc") == stable_uuid("user", "noc")
    assert stable_uuid("user", "noc") != stable_uuid("user", "approver")
    assert serial_for("dlp1-edge-01").startswith("DEMO")
    assert serial_for("dlp1-edge-01") == serial_for("dlp1-edge-01")


def test_the_tiny_fixture_renders_what_it_says(tmp_path: Path) -> None:
    files = generate(tmp_path, FIXTURES / "tiny.yaml")
    directory = yaml.safe_load(files["dist/bundles/00-organizations.yaml"])
    assert [o["slug"] for o in directory["organizations"]] == ["default", "tenant"]
    operator = yaml.safe_load(files["dist/bundles/10-default.yaml"])
    assert [d["name"] for d in operator["devices"]] == ["abc1-edge-01", "abc1-edge-02"]
    live = operator["devices"][0]
    assert live["mgmt_host"] == "172.28.103.21"
    assert live["attributes"]["simulated"] is True
    assert sorted(p for p in files if p.startswith("dist/lab/frr/")) == [
        "dist/lab/frr/abc1-edge-01.conf",
        "dist/lab/frr/abc1-edge-02.conf",
        "dist/lab/frr/isp.conf",
    ]


class TestExtends:
    def test_mappings_and_identified_lists_merge(self) -> None:
        base = {"a": {"x": 1, "y": 2}, "items": [{"id": "one", "v": 1}], "plain": [1, 2]}
        over = {"a": {"y": 3}, "items": [{"id": "one", "v": 9}, {"id": "two"}], "plain": [3]}
        assert merge(base, over) == {
            "a": {"x": 1, "y": 3},
            "items": [{"id": "one", "v": 9}, {"id": "two"}],
            "plain": [3],
        }

    def test_merge_leaves_its_inputs_alone(self) -> None:
        base = {"items": [{"id": "one", "v": 1}]}
        before = copy.deepcopy(base)
        merge(base, {"items": [{"id": "one", "v": 2}]})
        assert base == before

    def test_an_extended_spec_adds_and_overrides(self) -> None:
        model = build_model(load_spec(FIXTURES / "extended.yaml"))
        assert [o.slug for o in model.orgs] == ["default", "tenant", "other"]
        assert model.org("tenant").name == "Example Tenant"
        assert model.org("tenant").description == "Changed by the extension"
        assert [p.username for p in model.personas] == ["ops", "tenant-admin", "other-admin"]
        assert {s.code: s.status for s in model.sites} == {"abc1": "planned", "xyz1": "active"}

    def test_an_extends_loop_is_refused(self, tmp_path: Path) -> None:
        (tmp_path / "a.yaml").write_text("extends: b.yaml\n")
        (tmp_path / "b.yaml").write_text("extends: a.yaml\n")
        with pytest.raises(SpecError, match="extends loop"):
            load_spec(tmp_path / "a.yaml")


def _tiny() -> dict[str, Any]:
    return load_spec(FIXTURES / "tiny.yaml")


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda s: s.update(spec_version=2), "spec_version"),
        (lambda s: s["orgs"].pop(0), "'default' is required"),
        (lambda s: s["orgs"].append(dict(s["orgs"][1])), "unique"),
        (lambda s: s["groups"].update({"/Bad": {"nowhere": "admin"}}), "unknown org"),
        (lambda s: s["groups"].update({"/Bad": {"default": "root"}}), "unknown role"),
        (lambda s: s["personas"][0].update(groups=["/Missing"]), "unknown group"),
        (lambda s: s["sites"][0].update(code="toolong1"), "three letters"),
        (lambda s: s["sites"][0].update(status="broken"), "unknown status"),
        (lambda s: s["lab"].update(routers=["abc1-edge-09"]), "not a generated"),
        (lambda s: s["lab"]["links"].append(["isp", "nowhere"]), "not a lab router"),
        (lambda s: s["lab"].update(services_router="isp"), "services_router"),
        (lambda s: s.update(stories=[{"id": "x", "orgs": ["nowhere"]}]), "unknown org"),
    ],
)
def test_spec_mistakes_are_refused(change: Any, message: str) -> None:
    spec = _tiny()
    change(spec)
    with pytest.raises(SpecError, match=message):
        build_model(spec)
