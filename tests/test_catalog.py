# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The service catalogue: its spec checks, its inventory files and its release gate."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from hegemony_demo_gen.catalog import (
    ADDRESS_TYPE,
    SERVICE_TYPE,
    address_record,
    check_service_reference,
)
from hegemony_demo_gen.model import build_model
from hegemony_demo_gen.render import render_all
from hegemony_demo_gen.spec import SpecError, load_spec

from tests.test_platform_pin import read_pin

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "spec" / "basic.yaml"
INVENTORY = "dist/inventory/"
# The first Git inventory plugin release that reads object-types/ and objects/.
FIRST_PLUGIN_WITH_OBJECTS = (0, 5, 0)


def _spec(enabled: bool = True) -> dict[str, Any]:
    spec = load_spec(SPEC)
    spec["service_catalog"]["enabled"] = enabled
    return spec


def _render(spec: dict[str, Any]) -> dict[str, str]:
    return render_all(build_model(spec), ROOT / "stories")


def _s4_form(files: dict[str, str]) -> dict[str, Any]:
    bundle = yaml.safe_load(files["dist/bundles/10-default.yaml"])
    flow = next(f for f in bundle["flows"] if f["name"] == "Service as code")
    form: dict[str, Any] = flow["definition"]["form"]
    return form


def test_off_writes_no_catalogue_and_keeps_the_typed_form() -> None:
    files = _render(_spec(enabled=False))
    assert not [p for p in files if p.startswith((INVENTORY + "object", INVENTORY + "objects"))]
    form = _s4_form(files)
    fields = {n["id"]: n["data"] for n in form["nodes"] if n["kind"] == "field"}
    assert fields["f_service_name"]["field_type"] == "core.text"
    assert fields["f_service_address"]["field_type"] == "core.text"
    assert "edges" not in form


def test_on_writes_both_types_and_every_record() -> None:
    files = _render(_spec())
    written = sorted(p.removeprefix(INVENTORY) for p in files if p.startswith(INVENTORY + "obj"))
    assert written == [
        f"object-types/{SERVICE_TYPE}.yaml",
        f"object-types/{ADDRESS_TYPE}.yaml",
        f"objects/{SERVICE_TYPE}/portal.yaml",
        f"objects/{ADDRESS_TYPE}/portal-primary.yaml",
        f"objects/{ADDRESS_TYPE}/portal-replacement.yaml",
    ]
    for path in written:
        document = yaml.safe_load(files[INVENTORY + path])
        assert document["schema_version"] == 1
        if path.startswith("objects/"):
            # The folder under objects/ is the record's type.
            assert path.split("/")[1] == document["object_type"]


def test_every_address_names_its_service_twice_alike() -> None:
    files = _render(_spec())
    services = {
        yaml.safe_load(t)["external_id"]
        for p, t in files.items()
        if p.startswith(f"{INVENTORY}objects/{SERVICE_TYPE}/")
    }
    for path, text in files.items():
        if path.startswith(f"{INVENTORY}objects/{ADDRESS_TYPE}/"):
            record = yaml.safe_load(text)
            check_service_reference(record)
            assert record["attributes"]["service_id"] in services
            assert record["attributes"]["prefix_length"] == 32


def test_a_record_whose_attribute_and_relationship_disagree_is_refused() -> None:
    model = build_model(_spec())
    record = address_record(model.catalog.addresses()[0])
    record["relationships"][0]["target_external_id"] = "elsewhere"
    with pytest.raises(SpecError, match="does not match its service relationship"):
        check_service_reference(record)


def test_on_turns_the_s4_fields_into_a_cascade() -> None:
    form = _s4_form(_render(_spec()))
    fields = {n["id"]: n["data"] for n in form["nodes"] if n["kind"] == "field"}
    service, address = fields["f_service_name"], fields["f_service_address"]
    assert service["field_type"] == address["field_type"] == "core.enum"
    assert service["config"]["option_source"] == {
        "kind": "inventory.objects",
        "config": {"object_type": SERVICE_TYPE, "value_field": "external_id"},
    }
    assert address["config"]["option_source"]["config"] == {
        "object_type": ADDRESS_TYPE,
        "value_field": "attr.address",
    }
    assert (service["default_value"], address["default_value"]) == ("portal", "10.255.100.20")
    assert form["edges"] == [
        {
            "id": "e_service_addresses",
            "source": "f_service_name",
            "target": "f_service_address",
            "relations": [{"semantic_type": "options_filter", "value": "attr.service_id"}],
        }
    ]


def test_an_empty_catalogue_keeps_its_type_directories_and_the_typed_form() -> None:
    spec = _spec()
    spec["service_catalog"]["services"] = []
    files = _render(spec)
    assert files[f"{INVENTORY}objects/{SERVICE_TYPE}/.gitkeep"] == ""
    assert files[f"{INVENTORY}objects/{ADDRESS_TYPE}/.gitkeep"] == ""
    fields = {n["id"]: n["data"] for n in _s4_form(files)["nodes"] if n["kind"] == "field"}
    assert fields["f_service_name"]["field_type"] == "core.text"


def _address(spec: dict[str, Any], index: int = 0) -> dict[str, Any]:
    address: dict[str, Any] = spec["service_catalog"]["services"][0]["addresses"][index]
    return address


def _wider_prefixes(spec: dict[str, Any]) -> None:
    spec["lab"]["service_prefixes"] = "10.255.100.0/23"
    _address(spec).update(address="10.255.101.20")


def _no_git_site(spec: dict[str, Any]) -> None:
    for site in spec["sites"]:
        site["source"] = "bundle"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda s: _address(s).update(address="10.255.101.20"), "not a host address in"),
        (lambda s: _address(s).update(address="10.255.100.0"), "not a host address in"),
        (lambda s: _address(s).update(address="10.255.100.255"), "not a host address in"),
        (lambda s: _address(s).update(address="portal"), "not an IPv4 address"),
        (lambda s: _address(s, 1).update(address="10.255.100.20"), "used twice"),
        (lambda s: _address(s, 1).update(id="portal-primary"), "unique"),
        (lambda s: _address(s, 1).update(purpose="primary"), "exactly one primary"),
        (lambda s: _address(s, 1).update(purpose="backup"), "purpose must be"),
        (lambda s: s["service_catalog"]["services"][0].update(id="Portal"), "s4 service name"),
        (lambda s: s["service_catalog"]["services"][0].update(port=0), "port"),
        (lambda s: s["service_catalog"]["services"][0].update(port="443"), "port"),
        (lambda s: s["service_catalog"]["services"][0].update(environment="dev"), "environment"),
        (lambda s: s["service_catalog"].update(enabled="yes"), "true or false"),
        (_no_git_site, "needs a site with source: git"),
        (lambda s: s["service_catalog"]["services"][0].update(id="portal\n"), "s4 service name"),
        (lambda s: _address(s).update(id="portal-primary\n"), "id must match"),
        (_wider_prefixes, "which s4 accepts"),
    ],
)
def test_catalogue_mistakes_are_refused(change: Any, message: str) -> None:
    spec = _spec()
    change(spec)
    with pytest.raises(SpecError, match=message):
        build_model(spec)


def _plugin_version() -> tuple[int, ...]:
    wheels = read_pin()["HEGEMONY_PLUGIN_WHEELS"].split()
    for pair in wheels:
        match = re.search(r"/hegemony_inventory_git-(\d+)\.(\d+)\.(\d+)-", pair)
        if match:
            return tuple(int(x) for x in match.groups())
    raise AssertionError("platform.env pins no Git inventory plugin wheel")


def test_the_catalogue_is_on_only_with_releases_that_read_it() -> None:
    """An older plugin or platform fails the whole Git provider, planned sites included."""
    if not build_model(load_spec(SPEC)).catalog.enabled:
        return
    assert _plugin_version() >= FIRST_PLUGIN_WITH_OBJECTS, (
        "service_catalog is enabled but platform.env pins a Git inventory plugin older than 0.5.0"
    )
    assert not read_pin()["HEGEMONY_PLATFORM_VERSION"].startswith("placeholder-"), (
        "service_catalog is enabled but platform.env names no platform release"
    )


@pytest.mark.parametrize("service_id", ["no", "on", "null", "true"])
def test_a_yaml_keyword_service_id_stays_a_string_default(service_id: str) -> None:
    spec = _spec()
    spec["service_catalog"]["services"][0]["id"] = service_id
    for address in spec["service_catalog"]["services"][0]["addresses"]:
        address["id"] = f"{service_id}-{address['purpose']}"
    fields = {n["id"]: n["data"] for n in _s4_form(_render(spec))["nodes"] if n["kind"] == "field"}
    assert fields["f_service_name"]["default_value"] == service_id
    assert fields["f_service_address"]["default_value"] == "10.255.100.20"
