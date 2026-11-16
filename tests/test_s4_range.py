# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The s4 flow owns one range of the service prefixes, and s1 stays out of it.

s4's leftover check fails a run when a router carries an address in s4's range
other than the applied one. If that range covered s1's address, running the
walkthrough in order (s1, then s4) would fail s4 on an address s4 never set.
Every place that spells the range (OpenTofu validation, form validation, the
leftover check's line filter) must agree with S4_ADDRESSES.
"""

from __future__ import annotations

import ipaddress
import re
from pathlib import Path
from typing import Any

import yaml
from hegemony_demo_gen.catalog import S4_ADDRESSES

from tests.test_catalog import _render, _s4_form, _spec

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "dist" / "bundles" / "10-default.yaml"
SERVICE_TF = ROOT / "stories" / "s4-service-as-code" / "service.tf"
ALL = [str(a) for a in ipaddress.IPv4Network("10.255.100.0/24")]
HOSTS = {str(a) for a in S4_ADDRESSES.hosts()}


def _flow(name: str) -> dict[str, Any]:
    bundle = yaml.safe_load(BUNDLE.read_text(encoding="utf-8"))
    flow: dict[str, Any] = next(f for f in bundle["flows"] if f["name"] == name)
    return flow


def _node(flow: dict[str, Any], node_id: str) -> dict[str, Any]:
    node: dict[str, Any] = next(
        n for n in flow["definition"]["graph"]["nodes"] if n["id"] == node_id
    )
    return node


def _field(flow: dict[str, Any], field_id: str) -> dict[str, Any]:
    node: dict[str, Any] = next(
        n for n in flow["definition"]["form"]["nodes"] if n["data"].get("field_id") == field_id
    )
    return node


def test_the_opentofu_validation_accepts_exactly_the_s4_hosts() -> None:
    text = SERVICE_TF.read_text(encoding="utf-8")
    match = re.search(r'can\(regex\("(.+?)", var\.service_address\)\)', text)
    assert match
    pattern = match.group(1).replace("\\\\", "\\")
    assert {a for a in ALL if re.search(pattern, a)} == HOSTS


def test_the_typed_form_accepts_exactly_the_s4_hosts() -> None:
    # With the catalogue on (the committed spec) the form picks from the
    # catalogue, whose addresses the generator keeps inside S4_ADDRESSES.
    form = _s4_form(_render(_spec(enabled=False)))
    field = next(n for n in form["nodes"] if n["data"].get("field_id") == "service_address")
    pattern = field["data"]["config"]["validations"]["children"][0]["operand"]["value"]
    assert {a for a in ALL if re.search(pattern, a)} == HOSTS
    assert str(S4_ADDRESSES) in field["data"]["description"]


def test_the_leftover_check_judges_exactly_the_s4_range() -> None:
    params = _node(_flow("Service as code"), "no_leftover")["params"]
    # The lines FRR's `show interface lo json` prints for each address.
    picked = {a for a in ALL if re.search(params["line_filter"], f'"address":"{a}/32",')}
    assert picked == {str(a) for a in S4_ADDRESSES}


def test_s1_announces_outside_the_s4_range() -> None:
    field = _field(_flow("Announce service prefix"), "service_address")
    assert ipaddress.IPv4Address(field["data"]["default_value"]) not in S4_ADDRESSES
