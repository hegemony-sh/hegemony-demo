# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""`demo-gen`: write (or with --check, verify) the generated files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .model import build_model
from .render import render_all
from .spec import SpecError, load_spec

# Trees the generator owns completely: anything else in them is stale.
OWNED = ("dist", "docs/_generated")


def find_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "spec").is_dir() and (candidate / "pyproject.toml").is_file():
            return candidate
    raise SpecError(f"no demo repository (spec/ and pyproject.toml) at or above {start}")


def generate(root: Path, spec: Path) -> dict[str, str]:
    model = build_model(load_spec(spec))
    return render_all(model, root / "stories")


def owned_files(root: Path) -> set[str]:
    found: set[str] = set()
    for tree in OWNED:
        base = root / tree
        if base.is_dir():
            found.update(p.relative_to(root).as_posix() for p in base.rglob("*") if p.is_file())
    return found


def check(root: Path, files: dict[str, str]) -> list[str]:
    problems: list[str] = []
    for path, text in sorted(files.items()):
        target = root / path
        if not target.is_file():
            problems.append(f"missing: {path}")
        elif target.read_text(encoding="utf-8") != text:
            problems.append(f"differs: {path}")
    problems.extend(f"stale:   {p}" for p in sorted(owned_files(root) - set(files)))
    return problems


def write(root: Path, files: dict[str, str]) -> None:
    for path in sorted(owned_files(root) - set(files)):
        (root / path).unlink()
    for path, text in sorted(files.items()):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or target.read_text(encoding="utf-8") != text:
            target.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="demo-gen", description=__doc__)
    parser.add_argument("--spec", type=Path, help="spec file (default: spec/basic.yaml)")
    parser.add_argument("--root", type=Path, help="repository root (default: found from cwd)")
    parser.add_argument(
        "--check", action="store_true", help="fail if the committed output is not current"
    )
    args = parser.parse_args(argv)
    try:
        root = (args.root or find_root(Path.cwd())).resolve()
        files = generate(root, args.spec or root / "spec" / "basic.yaml")
    except (SpecError, OSError) as exc:
        print(f"demo-gen: {exc}", file=sys.stderr)
        return 2
    if args.check:
        problems = check(root, files)
        if problems:
            print("demo-gen: generated files are not current; run `uv run demo-gen`:")
            print("\n".join(f"  {p}" for p in problems))
            return 1
        print(f"demo-gen: {len(files)} generated files are current")
        return 0
    write(root, files)
    print(f"demo-gen: wrote {len(files)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
