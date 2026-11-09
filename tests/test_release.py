# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""scripts/release_check.py: which tags may be released."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "release_check", ROOT / "scripts/release_check.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["release_check"] = module
    spec.loader.exec_module(module)
    return module


release_check = _load()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "spec").mkdir()
    monkeypatch.setattr(release_check, "ROOT", tmp_path)
    return tmp_path


def _write(repo: Path, version: str, ref: str) -> None:
    (repo / "platform.env").write_text(f"HEGEMONY_PLATFORM_VERSION={version}\n")
    (repo / "spec" / "basic.yaml").write_text(f"inventory:\n  ref: {ref}\n")


@pytest.mark.parametrize("tag", ["v1.0.0", "v1.0.0+demo.2", "v1.0.0-rc.1"])
def test_a_matching_tag_may_be_released(repo: Path, tag: str) -> None:
    version = tag[1:].split("+")[0]
    _write(repo, version, tag)
    assert release_check.problems(tag) == []


@pytest.mark.parametrize("tag", ["1.0.0", "v1.0", "v2026.11.01", "v1.0.0+demo.0", "v1.0.0-demo.1"])
def test_a_malformed_tag_is_refused(repo: Path, tag: str) -> None:
    _write(repo, "1.0.0", tag)
    assert release_check.problems(tag)


def test_the_placeholder_is_refused(repo: Path) -> None:
    _write(repo, "placeholder-9.9.9-rc", "v1.0.0")
    assert "placeholder" in release_check.problems("v1.0.0")[0]


def test_a_tag_for_another_platform_is_refused(repo: Path) -> None:
    _write(repo, "1.0.1", "v1.0.0")
    assert "platform.env pins 1.0.1" in release_check.problems("v1.0.0")[0]


def test_the_committed_tree_is_not_releasable_while_the_pin_is_a_placeholder() -> None:
    pin = (ROOT / "platform.env").read_text()
    if "HEGEMONY_PLATFORM_VERSION=placeholder-" in pin:
        assert release_check.problems("v1.0.0")
