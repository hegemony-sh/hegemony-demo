# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""scripts/latest_release.py: the newest platform release and the wheels it was built with."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 64
WHEEL_URL = (
    "https://github.com/hegemony-sh/hegemony-inventory-plugins/releases/download/"
    "v0.6.0/hegemony_inventory_git-0.6.0-py3-none-any.whl"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "latest_release", ROOT / "scripts" / "latest_release.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["latest_release"] = module
    spec.loader.exec_module(module)
    return module


lr = _load()


def _release(
    tag: str, at: str = "2026-01-01T00:00:00Z", *, draft: bool = False, assets: list | None = None
) -> dict:
    return {"tag_name": tag, "published_at": at, "draft": draft, "assets": assets or []}


def _asset(name: str, url: str = WHEEL_URL, digest: str = f"sha256:{SHA}") -> dict:
    return {"name": name, "browser_download_url": url, "digest": digest}


def test_the_most_recently_published_release_wins_over_a_higher_number() -> None:
    # The repository still lists pre-launch releases numbered above the candidates.
    releases = [
        _release("v5.0.0", "2026-09-01T10:00:00Z"),
        _release("v9.9.0-rc.2", "2026-11-01T10:00:00Z"),
        _release("v9.9.0-rc.3", "2026-11-02T10:00:00Z"),
    ]
    assert lr.pick_latest(releases) == "9.9.0-rc.3"
    assert lr.pick_latest([*releases, _release("v9.9.0", "2026-11-03T10:00:00Z")]) == "9.9.0"


def test_drafts_and_other_tags_are_not_published_releases() -> None:
    releases = [
        _release("v9.9.0-rc.2", "2026-11-01T10:00:00Z"),
        _release("v9.9.0-rc.3", "2026-11-02T10:00:00Z", draft=True),
        _release("nightly", "2026-11-03T10:00:00Z"),
        {"tag_name": "v9.9.0-rc.4", "published_at": None, "draft": False},
    ]
    assert lr.pick_latest(releases) == "9.9.0-rc.2"
    with pytest.raises(LookupError):
        lr.pick_latest([_release("v9.9.0", draft=True)])


def test_the_wheel_comes_with_its_published_digest() -> None:
    release = _release(
        "v0.6.0",
        assets=[
            _asset("hegemony_inventory_git-0.6.0-py3-none-any.whl"),
            _asset("hegemony_inventory_netbox-0.6.0-py3-none-any.whl"),
            _asset("SHA256SUMS"),
        ],
    )
    assert lr.wheel_pair(release, "hegemony_inventory_git-") == f"{SHA}@{WHEEL_URL}"


@pytest.mark.parametrize(
    "assets",
    [
        [],
        [_asset("hegemony_inventory_git-0.6.0-py3-none-any.whl", digest="")],
        [
            _asset("hegemony_inventory_git-0.6.0-py3-none-any.whl"),
            _asset("hegemony_inventory_git-0.6.0-py3-none-any.whl"),
        ],
    ],
)
def test_a_missing_ambiguous_or_unhashed_wheel_is_refused(assets: list[dict]) -> None:
    with pytest.raises(LookupError):
        lr.wheel_pair(_release("v0.6.0", assets=assets), "hegemony_inventory_git-")


def test_render_replaces_only_the_two_pins() -> None:
    text = (
        "# a comment that mentions HEGEMONY_PLATFORM_VERSION\n"
        "HEGEMONY_PLATFORM_VERSION=9.9.0-rc.1\n"
        "HEGEMONY_PLATFORM_REPO=https://github.com/hegemony-sh/hegemony.git\n"
        'HEGEMONY_PLUGIN_WHEELS="old@https://example.invalid/x.whl"\n'
    )
    out = lr.render(text, "9.9.0-rc.3", f"{SHA}@{WHEEL_URL}")
    assert lr.pinned(out) == ("9.9.0-rc.3", f"{SHA}@{WHEEL_URL}")
    assert out.splitlines()[0] == "# a comment that mentions HEGEMONY_PLATFORM_VERSION"
    assert "HEGEMONY_PLATFORM_REPO=https://github.com/hegemony-sh/hegemony.git" in out


def test_resolve_takes_the_wheels_from_the_plugin_releases_the_platform_pins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refs = {repo.split("/", 1)[1]: f"v0.{i}.0" for i, (repo, _) in enumerate(lr.WHEELS)}
    pins = {name: {"ref": ref, "commit": "0" * 40} for name, ref in refs.items()}
    assets: dict[str, list[dict]] = {}
    expected = []
    for repo, prefix in lr.WHEELS:
        ref = refs[repo.split("/", 1)[1]]
        name = f"{prefix}{ref[1:]}-py3-none-any.whl"
        url = f"https://github.com/{repo}/releases/download/{ref}/{name}"
        assets.setdefault(repo, []).append(_asset(name, url=url))
        expected.append(f"{SHA}@{url}")
    answers = {
        "/repos/hegemony-sh/hegemony/releases?per_page=100": [
            _release("v9.9.0-rc.3", "2026-11-02T10:00:00Z"),
            _release("v9.9.0-rc.2", "2026-11-01T10:00:00Z"),
        ],
        "/repos/hegemony-sh/hegemony/contents/.github/plugin-pins.json?ref=v9.9.0-rc.3": pins,
    }
    for repo, repo_assets in assets.items():
        ref = refs[repo.split("/", 1)[1]]
        answers[f"/repos/{repo}/releases/tags/{ref}"] = _release(ref, assets=repo_assets)
    calls: list[str] = []

    def get(path: str, accept: str = "") -> bytes:
        calls.append(path)
        return json.dumps(answers[path]).encode()

    monkeypatch.setattr(lr, "_get", get)
    assert lr.resolve() == ("9.9.0-rc.3", " ".join(expected))
    # One request per plugin release, however many wheels it supplies.
    assert len(calls) == len(set(calls)) == len(answers)


def test_the_demo_adds_a_plugin_from_each_plugin_repository() -> None:
    assert {repo for repo, _ in lr.WHEELS} == {
        "hegemony-sh/hegemony-inventory-plugins",
        "hegemony-sh/hegemony-notification-plugins",
        "hegemony-sh/hegemony-secret-plugins",
        "hegemony-sh/hegemony-step-plugins",
    }


def test_check_fails_when_the_pin_is_older(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "platform.env").write_text(
        f'HEGEMONY_PLATFORM_VERSION=9.9.0-rc.2\nHEGEMONY_PLUGIN_WHEELS="{SHA}@{WHEEL_URL}"\n'
    )
    monkeypatch.setattr(lr, "ROOT", tmp_path)
    monkeypatch.setattr(lr, "resolve", lambda: ("9.9.0-rc.3", f"{SHA}@{WHEEL_URL}"))
    assert lr.main(["latest_release.py", "check"]) == 1
    assert "the newest release is 9.9.0-rc.3" in capsys.readouterr().err

    assert lr.main(["latest_release.py", "write"]) == 0
    assert lr.main(["latest_release.py", "check"]) == 0


def test_platform_env_pins_one_wheel_per_listed_plugin() -> None:
    _, wheels = lr.pinned((ROOT / "platform.env").read_text())
    names = [pair.rsplit("/", 1)[1] for pair in wheels.split()]
    assert len(names) == len(lr.WHEELS)
    for repo, prefix in lr.WHEELS:
        matching = [pair for pair in wheels.split() if pair.rsplit("/", 1)[1].startswith(prefix)]
        assert len(matching) == 1, prefix
        assert f"https://github.com/{repo}/releases/download/" in matching[0]
