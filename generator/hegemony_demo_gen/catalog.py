# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The service catalogue: repository-defined inventory types in the Git inventory.

The Git inventory plugin (0.5.0 and later) reads `object-types/*.yaml`
definitions and `objects/<type>/*.yaml` records next to the planned sites. The
demo declares two types: a service, and the addresses a service answers on.
The s4 form then picks a service and one of its addresses from them.

The plugin validates the files against their JSON Schema but cannot check what
the schema language here leaves out: that an address is an IPv4 host inside the
lab's service prefixes, or that a record's `service_id` attribute names the
same service as its `service` relationship. The model and the renderer check
both, so a spec mistake fails `demo-gen` instead of the provider's sync.

The catalogue is off unless the spec sets `service_catalog.enabled`: a platform
or plugin release older than the one that reads these files fails the whole Git
provider, the planned sites included.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Any

from .spec import SpecError

# Type ids are the repository's own; the prefix keeps them apart from any other
# source's types (the platform refuses two different schemas under one id).
SERVICE_TYPE = "demo.service"
ADDRESS_TYPE = "demo.service_address"
# The s4 flow writes the service id into router configuration and its OpenTofu
# variable validation accepts exactly this shape (stories/s4-service-as-code).
SERVICE_ID = re.compile(r"^[a-z][a-z0-9-]{1,30}$")
RECORD_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,99}$")
ENVIRONMENTS = ("production", "staging")
PURPOSES = ("primary", "replacement")
# Each address is announced as a host route.
HOST_PREFIX_LENGTH = 32
# The addresses the s4 flow's OpenTofu validation and form accept: hosts .1 to
# .254 of this network, whatever lab.service_prefixes says.
S4_ADDRESSES = ipaddress.IPv4Network("10.255.100.0/24")


@dataclass(frozen=True)
class ServiceAddress:
    id: str
    name: str
    service_id: str
    address: str
    purpose: str


@dataclass(frozen=True)
class Service:
    id: str
    name: str
    owner: str
    environment: str
    port: int
    enabled: bool
    labels: tuple[str, ...]
    verification_timeout_seconds: int
    require_approval: bool
    addresses: tuple[ServiceAddress, ...]


@dataclass(frozen=True)
class ServiceCatalog:
    enabled: bool
    services: tuple[Service, ...]

    def addresses(self) -> list[ServiceAddress]:
        return [a for s in self.services for a in s.addresses]

    @property
    def in_forms(self) -> bool:
        """Whether forms pick services from the catalogue (on, with a service)."""
        return self.enabled and bool(self.services)

    def primary(self, service_id: str) -> ServiceAddress:
        service = next(s for s in self.services if s.id == service_id)
        return next(a for a in service.addresses if a.purpose == "primary")


def _require(data: dict[str, Any], key: str, where: str) -> Any:
    if not isinstance(data, dict) or key not in data:
        raise SpecError(f"{where}: {key} is required")
    return data[key]


def _int(value: Any, where: str, low: int, high: int | None = None) -> int:
    if type(value) is not int or value < low or (high is not None and value > high):
        bound = f"{low}..{high}" if high is not None else f">= {low}"
        raise SpecError(f"{where}: expected an integer {bound}")
    return value


def _bool(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise SpecError(f"{where}: expected true or false")
    return value


def build_catalog(raw: Any, service_prefixes: str) -> ServiceCatalog:
    """Validate the spec's `service_catalog` section; absent means off and empty."""
    if raw is None:
        return ServiceCatalog(enabled=False, services=())
    if not isinstance(raw, dict):
        raise SpecError("service_catalog: expected a mapping")
    enabled = _bool(raw.get("enabled", False), "service_catalog.enabled")
    prefixes = ipaddress.IPv4Network(service_prefixes)
    services: list[Service] = []
    seen_records: set[str] = set()
    seen_addresses: set[str] = set()
    for item in raw.get("services") or []:
        sid = str(_require(item, "id", "service_catalog.services[]"))
        where = f"service {sid}"
        if not SERVICE_ID.fullmatch(sid):
            raise SpecError(f"{where}: id must match {SERVICE_ID.pattern} (the s4 service name)")
        if any(s.id == sid for s in services):
            raise SpecError(f"{where}: ids must be unique")
        environment = str(_require(item, "environment", where))
        if environment not in ENVIRONMENTS:
            raise SpecError(f"{where}: environment must be one of {', '.join(ENVIRONMENTS)}")
        labels = item.get("labels") or []
        if not isinstance(labels, list) or not all(isinstance(x, str) for x in labels):
            raise SpecError(f"{where}: labels must be a list of strings")
        addresses: list[ServiceAddress] = []
        for entry in item.get("addresses") or []:
            aid = str(_require(entry, "id", f"{where} addresses[]"))
            awhere = f"{where} address {aid}"
            if not RECORD_ID.fullmatch(aid):
                raise SpecError(f"{awhere}: id must match {RECORD_ID.pattern}")
            if aid in seen_records:
                raise SpecError(f"{awhere}: address ids must be unique")
            seen_records.add(aid)
            try:
                host = ipaddress.IPv4Address(str(_require(entry, "address", awhere)))
            except ipaddress.AddressValueError as exc:
                raise SpecError(f"{awhere}: not an IPv4 address") from exc
            if host not in prefixes or host in (
                prefixes.network_address,
                prefixes.broadcast_address,
            ):
                raise SpecError(f"{awhere}: {host} is not a host address in {prefixes}")
            if host not in S4_ADDRESSES or host in (
                S4_ADDRESSES.network_address,
                S4_ADDRESSES.broadcast_address,
            ):
                raise SpecError(
                    f"{awhere}: {host} is not a host in {S4_ADDRESSES}, which s4 accepts"
                )
            if str(host) in seen_addresses:
                raise SpecError(f"{awhere}: {host} is used twice")
            seen_addresses.add(str(host))
            purpose = str(_require(entry, "purpose", awhere))
            if purpose not in PURPOSES:
                raise SpecError(f"{awhere}: purpose must be one of {', '.join(PURPOSES)}")
            addresses.append(
                ServiceAddress(
                    id=aid,
                    name=str(_require(entry, "name", awhere)),
                    service_id=sid,
                    address=str(host),
                    purpose=purpose,
                )
            )
        if [a.purpose for a in addresses].count("primary") != 1:
            raise SpecError(f"{where}: needs exactly one primary address")
        services.append(
            Service(
                id=sid,
                name=str(_require(item, "name", where)),
                owner=str(_require(item, "owner", where)),
                environment=environment,
                port=_int(_require(item, "port", where), f"{where}.port", 1, 65535),
                enabled=_bool(item.get("enabled", True), f"{where}.enabled"),
                labels=tuple(labels),
                verification_timeout_seconds=_int(
                    item.get("verification_timeout_seconds", 120),
                    f"{where}.verification_timeout_seconds",
                    1,
                ),
                require_approval=_bool(
                    item.get("require_approval", True), f"{where}.require_approval"
                ),
                addresses=tuple(addresses),
            )
        )
    return ServiceCatalog(enabled=enabled, services=tuple(services))


# --------------------------------------------------------------------------- files


def service_type() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "object_type",
        "id": SERVICE_TYPE,
        "display_name": "Service",
        "plural": "Services",
        "group": "Service catalogue",
        "field_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["owner", "environment", "port", "enabled"],
            "properties": {
                "owner": {"type": "string"},
                "environment": {"type": "string", "enum": list(ENVIRONMENTS)},
                "port": {"type": "integer", "minimum": 1, "maximum": 65535},
                "enabled": {"type": "boolean"},
                "labels": {"type": "array", "items": {"type": "string"}},
                "settings": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "verification_timeout_seconds": {"type": "integer", "minimum": 1},
                        "require_approval": {"type": "boolean"},
                    },
                },
            },
        },
        "filters": ["owner", "environment", "enabled"],
        "ui": {
            "columns": ["name", "owner", "environment", "port", "enabled"],
            "detail_layout": ["owner", "environment", "port", "enabled", "labels", "settings"],
            "search_fields": ["owner", "environment"],
            "default_sort": "name",
        },
    }


def address_type() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "object_type",
        "id": ADDRESS_TYPE,
        "display_name": "Service address",
        "plural": "Service addresses",
        "group": "Service catalogue",
        "field_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["service_id", "address", "prefix_length", "purpose"],
            "properties": {
                "service_id": {"type": "string"},
                "address": {"type": "string"},
                "prefix_length": {"type": "integer", "minimum": 0, "maximum": 32},
                "purpose": {"type": "string", "enum": list(PURPOSES)},
            },
        },
        "relationships": [
            {"rel": "service", "target_object_type": SERVICE_TYPE, "required": True, "many": False}
        ],
        "filters": ["service_id", "purpose"],
        "ui": {
            "columns": ["name", "service_id", "address", "prefix_length", "purpose"],
            "detail_layout": ["service_id", "address", "prefix_length", "purpose"],
            "search_fields": ["address", "service_id"],
            "default_sort": "name",
        },
    }


def service_record(service: Service) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "object",
        "object_type": SERVICE_TYPE,
        "external_id": service.id,
        "name": service.name,
        "attributes": {
            "owner": service.owner,
            "environment": service.environment,
            "port": service.port,
            "enabled": service.enabled,
            "labels": list(service.labels),
            "settings": {
                "verification_timeout_seconds": service.verification_timeout_seconds,
                "require_approval": service.require_approval,
            },
        },
    }


def address_record(address: ServiceAddress) -> dict[str, Any]:
    record = {
        "schema_version": 1,
        "kind": "object",
        "object_type": ADDRESS_TYPE,
        "external_id": address.id,
        "name": address.name,
        "attributes": {
            "service_id": address.service_id,
            "address": address.address,
            "prefix_length": HOST_PREFIX_LENGTH,
            "purpose": address.purpose,
        },
        "relationships": [
            {
                "rel": "service",
                "target_object_type": SERVICE_TYPE,
                "target_external_id": address.service_id,
            }
        ],
    }
    check_service_reference(record)
    return record


def check_service_reference(record: dict[str, Any]) -> None:
    """The `service_id` attribute and the `service` relationship name one service.

    The attribute drives the form's `attr.service_id` cascade; the relationship
    is what the plugin checks exists. Nothing in the file format ties the two.
    """
    targets = [
        r["target_external_id"]
        for r in record.get("relationships", [])
        if r.get("rel") == "service" and r.get("target_object_type") == SERVICE_TYPE
    ]
    if targets != [record["attributes"]["service_id"]]:
        raise SpecError(
            f"{ADDRESS_TYPE} {record['external_id']}: service_id "
            f"{record['attributes']['service_id']!r} does not match its service relationship"
        )


def catalog_files(catalog: ServiceCatalog) -> dict[str, dict[str, Any] | None]:
    """Paths under the inventory root to their document; None is an empty `.gitkeep`.

    A declared type needs its object directory even with no records, and Git
    does not keep an empty directory.
    """
    if not catalog.enabled:
        return {}
    files: dict[str, dict[str, Any] | None] = {
        f"object-types/{SERVICE_TYPE}.yaml": service_type(),
        f"object-types/{ADDRESS_TYPE}.yaml": address_type(),
    }
    for service in catalog.services:
        files[f"objects/{SERVICE_TYPE}/{service.id}.yaml"] = service_record(service)
    for address in catalog.addresses():
        files[f"objects/{ADDRESS_TYPE}/{address.id}.yaml"] = address_record(address)
    for type_id in (SERVICE_TYPE, ADDRESS_TYPE):
        if not any(p.startswith(f"objects/{type_id}/") for p in files):
            files[f"objects/{type_id}/.gitkeep"] = None
    return files
