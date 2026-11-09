# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Theme lint: words that must not come back, and theme-free identifiers.

The demo once used names from a fictional world whose rights holder enforces
its marks, and an earlier "Meridian" design, and it carried an IOS XE upgrade
story. None of that belongs here. This scans every file of the repository,
hand-written and generated, except this one.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml
from hegemony_demo_gen.model import build_model
from hegemony_demo_gen.spec import load_spec

ROOT = Path(__file__).resolve().parents[1]

BANNED = [
    # The earlier design and its leftovers.
    r"meridian", r"mer-palantir", r"acme", r"globex", r"legacy-radius", r"partner-api",
    # The fictional world, its places and people.
    r"tolkien", r"middle[- ]earth", r"gondor", r"rohan", r"shire", r"shirriff", r"palantir",
    r"elrond", r"gandalf", r"aragorn", r"galadriel", r"faramir", r"[eé]owyn", r"[eé]omer",
    r"samwise", r"frodo", r"bilbo", r"gimli", r"balin", r"durin'?s?", r"saruman", r"sauron",
    r"isengard", r"mordor", r"minas tirith", r"rivendell", r"lothl[oó]rien", r"moria",
    r"erebor", r"edoras", r"hobbit(s|on)?", r"buckland", r"michel delving", r"osgiliath",
    r"dol amroth", r"helm'?s deep", r"hornburg", r"fangorn", r"riddermark", r"elven",
    r"dwarven", r"beacon routers?",
    # The IOS XE upgrade story and its fake image.
    r"iosxe", r"cisco[._-]iosxe", r"steps[._-]cisco", r"cat9k",
    r"ios[- ]?xe\W{1,3}(image\W{1,3})?upgrades?", r"upgrades?\W{1,3}(to\W{1,3})?ios[- ]?xe",
]  # fmt: skip
BANNED_RE = re.compile(r"\b(" + "|".join(BANNED) + r")\b", re.IGNORECASE)
SELF = Path(__file__).resolve()


def repository_files() -> list[Path]:
    try:
        listed = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout.split(b"\0")
        files = [ROOT / name.decode() for name in listed if name]
    except (OSError, subprocess.CalledProcessError):
        skip = {".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
        files = [p for p in ROOT.rglob("*") if p.is_file() and not skip & set(p.parts)]
    return sorted(p for p in files if p.is_file() and p.resolve() != SELF)


def test_the_pattern_catches_what_it_should() -> None:
    for text in ("Meridian-Signature", "Minas Tirith", "cisco.iosxe.upgrade", "IOS XE upgrade"):
        assert BANNED_RE.search(text), text
    for text in ("ios-xe", "platform: ios-xe", "Amphictyon", "upgrade the platform", "Hampshire"):
        assert not BANNED_RE.search(text), text


def test_no_banned_word_anywhere() -> None:
    hits = []
    for path in repository_files():
        rel = path.relative_to(ROOT).as_posix()
        for match in BANNED_RE.finditer(rel):
            hits.append(f"{rel}: file name: {match.group(0)}")
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            for match in BANNED_RE.finditer(line):
                hits.append(f"{rel}:{number}: {match.group(0)}")
    assert not hits, "banned words:\n" + "\n".join(hits)


def test_no_firmware_images() -> None:
    images = [p for p in repository_files() if p.suffix.lower() in {".bin", ".img", ".iso"}]
    assert images == []


def theme_words() -> set[str]:
    model = build_model(load_spec(ROOT / "spec" / "basic.yaml"))
    words: set[str] = set()
    names = [model.operator, model.region_root]
    names += [o.name for o in model.orgs] + [o.region or "" for o in model.orgs]
    names += [s.name for s in model.sites] + [p.persona for p in model.personas]
    names += [c.name for c in model.contacts.values()]
    for name in names:
        words.update(w.lower() for w in re.findall(r"[A-Za-z]{4,}", name))
    return words - {"networks", "oracle"}


IDENTIFIER_SECTIONS = {
    "secrets": "name",
    "flows": "name",
    "flow_attachments": "filename",
    "notification_destinations": "name",
    "variables": "name",
    "schedules": "name",
    "git_repositories": "name",
    "inventory_providers": "name",
}


@pytest.mark.parametrize("bundle", sorted((ROOT / "dist" / "bundles").glob("*.yaml")))
def test_technical_identifiers_are_theme_free(bundle: Path) -> None:
    words = theme_words()
    data = yaml.safe_load(bundle.read_text())
    for section, key in IDENTIFIER_SECTIONS.items():
        for item in data.get(section, []):
            tokens = {t.lower() for t in re.findall(r"[A-Za-z]+", str(item[key]))}
            assert not tokens & words, (bundle.name, section, item[key])
