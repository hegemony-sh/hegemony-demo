# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Load a spec file, resolving `extends` by deep merge."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# Keys that identify an item in a list of mappings, tried in this order. Lists
# whose items carry one of them merge item by item; other lists are replaced.
IDENTITY_KEYS = ("id", "slug", "username", "code")


class SpecError(ValueError):
    """The spec is malformed or inconsistent."""


def _identity(item: object) -> tuple[str, Any] | None:
    if not isinstance(item, dict):
        return None
    for key in IDENTITY_KEYS:
        if key in item:
            return key, item[key]
    return None


def merge(base: Any, override: Any) -> Any:
    """Deep-merge `override` into `base` and return the result (inputs untouched).

    Mappings merge by key. Lists of mappings that carry an identity key merge by
    that key: a matching item merges, a new item is appended in order. Any
    other value in `override` replaces the one in `base`.
    """
    if isinstance(base, dict) and isinstance(override, dict):
        out = dict(base)
        for key, value in override.items():
            out[key] = merge(base[key], value) if key in base else value
        return out
    if isinstance(base, list) and isinstance(override, list):
        ids = [_identity(item) for item in base]
        if base and all(ids) and all(_identity(item) for item in override):
            out_list = list(base)
            for item in override:
                ident = _identity(item)
                if ident in ids:
                    index = ids.index(ident)
                    out_list[index] = merge(out_list[index], item)
                else:
                    out_list.append(item)
                    ids.append(ident)
            return out_list
    return override


def load_spec(path: Path, _seen: tuple[Path, ...] = ()) -> dict[str, Any]:
    """Read a spec, following `extends` (relative to the file) recursively."""
    path = path.resolve()
    if path in _seen:
        chain = " -> ".join(p.name for p in (*_seen, path))
        raise SpecError(f"extends loop: {chain}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        raise SpecError(f"{path}: not readable YAML: {exc}") from None
    if not isinstance(data, dict):
        raise SpecError(f"{path}: a spec is a mapping")
    parent = data.pop("extends", None)
    if parent is None:
        return data
    if not isinstance(parent, str):
        raise SpecError(f"{path}: extends names one spec file")
    base = load_spec(path.parent / parent, (*_seen, path))
    merged = merge(base, data)
    if not isinstance(merged, dict):
        raise SpecError(f"{path}: merge did not produce a mapping")
    return merged
