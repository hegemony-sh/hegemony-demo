# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The demo model: the spec, validated and expanded into concrete records."""

from __future__ import annotations

import hashlib
import ipaddress
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from .catalog import ServiceCatalog, build_catalog
from .spec import SpecError

# Every generated id derives from this namespace, so ids are stable across runs.
NAMESPACE = uuid.UUID("6f1d8a52-3c1e-5b7e-9a43-0d5e1c2b7f10")

ORG_ROLES = ("admin", "editor", "operator", "approver", "auditor", "viewer")
REALM_ROLES = ORG_ROLES
SITE_STATUSES = ("active", "planned", "staging", "decommissioning")
DEVICE_ROLES = ("edge", "core", "acc", "oob", "srv")
SLUG = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
SITE_CODE = re.compile(r"^[a-z]{3}[0-9]$")


def stable_uuid(*parts: str) -> str:
    """A UUID that depends only on `parts`."""
    return str(uuid.uuid5(NAMESPACE, "/".join(parts)))


def serial_for(name: str) -> str:
    """A clearly synthetic serial number: `DEMO` and a hash of the device name."""
    return "DEMO" + hashlib.sha256(name.encode()).hexdigest()[:8].upper()


@dataclass(frozen=True)
class Org:
    slug: str
    name: str
    description: str
    region: str | None
    shared: bool
    variables: dict[str, str]


@dataclass(frozen=True)
class Persona:
    username: str
    persona: str
    role: str
    groups: tuple[str, ...]
    about: str


@dataclass(frozen=True)
class Site:
    code: str
    name: str
    org: str
    group: str
    status: str
    profile: str
    source: str
    index: int  # 1-based position in the spec; picks the site's address block


@dataclass(frozen=True)
class Device:
    name: str
    site: str
    org: str
    role: str
    vendor: str
    model: str
    platform: str
    mgmt_host: str
    loopback: str
    serial: str
    live: bool


@dataclass(frozen=True)
class LabNode:
    """A container of the lab: a router (FRR) or a Linux server."""

    name: str
    kind: str  # "router" or "server"
    org: str | None  # None for the upstream provider, which no organization manages
    mgmt_ip: str
    loopback: str | None
    asn: int | None
    lan: tuple[str, ...] = ()  # server: its addresses on the services LAN


@dataclass(frozen=True)
class Link:
    """A point-to-point link between two routers: one small Docker network."""

    network: str
    subnet: str
    a: str
    a_ip: str
    b: str
    b_ip: str
    protocol: str  # "ospf" inside the operator's network, "ebgp" to the provider

    def peer(self, name: str) -> tuple[str, str]:
        """The other end's name and address, seen from `name`."""
        return (self.b, self.b_ip) if name == self.a else (self.a, self.a_ip)

    def address(self, name: str) -> str:
        return self.a_ip if name == self.a else self.b_ip


@dataclass(frozen=True)
class Lab:
    management: str
    management_network: str  # the Docker network's fixed name
    asn: int
    upstream: LabNode
    upstream_prefix: str
    services: str  # the server LAN behind `services_router`
    services_router: str
    services_router_ip: str
    service_prefixes: str  # what s1 and s5 announce; the edges export it upstream
    nodes: list[LabNode]
    links: list[Link]

    def node(self, name: str) -> LabNode:
        if name == self.upstream.name:
            return self.upstream
        return next(n for n in self.nodes if n.name == name)

    def routers(self) -> list[LabNode]:
        return [self.upstream] + [n for n in self.nodes if n.kind == "router"]

    def servers(self) -> list[LabNode]:
        return [n for n in self.nodes if n.kind == "server"]

    def links_of(self, name: str) -> list[Link]:
        return [link for link in self.links if name in (link.a, link.b)]


@dataclass(frozen=True)
class Story:
    id: str
    orgs: tuple[str, ...]


@dataclass(frozen=True)
class Contact:
    org: str
    name: str
    mailbox: str


@dataclass
class Model:
    spec_id: str
    operator: str
    domain: str
    region_root: str
    orgs: list[Org]
    groups: dict[str, dict[str, str]]
    personas: list[Persona]
    sites: list[Site]
    devices: list[Device]
    stories: list[Story]
    contacts: dict[str, Contact]
    lab: Lab
    extra: dict[str, Any] = field(default_factory=dict)
    catalog: ServiceCatalog = field(
        default_factory=lambda: ServiceCatalog(enabled=False, services=())
    )

    def org(self, slug: str) -> Org:
        for org in self.orgs:
            if org.slug == slug:
                return org
        raise KeyError(slug)

    def sites_of(self, org: str) -> list[Site]:
        return [s for s in self.sites if s.org == org]

    def devices_of(self, org: str, *, source: str | None = None) -> list[Device]:
        codes = {s.code for s in self.sites if source is None or s.source == source}
        return [d for d in self.devices if d.org == org and d.site in codes]

    def live_devices(self) -> list[Device]:
        return [d for d in self.devices if d.live]

    def device(self, name: str) -> Device:
        return next(d for d in self.devices if d.name == name)

    def email(self, mailbox: str, org: str | None = None) -> str:
        if org is None or org == "default":
            return f"{mailbox}@{self.domain}"
        return f"{mailbox}@{org}.{self.domain}"


def _require(data: dict[str, Any], key: str, where: str) -> Any:
    if key not in data:
        raise SpecError(f"{where}: missing '{key}'")
    return data[key]


def _str_map(value: Any, where: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise SpecError(f"{where}: expected a mapping")
    return {str(k): str(v) for k, v in value.items()}


def build_model(spec: dict[str, Any]) -> Model:
    """Validate `spec` and expand it into concrete records."""
    if spec.get("spec_version") != 1:
        raise SpecError("spec_version must be 1")
    theme = _require(spec, "theme", "spec")

    orgs: list[Org] = []
    for raw in _require(spec, "orgs", "spec"):
        slug = str(_require(raw, "slug", "orgs[]"))
        if not SLUG.match(slug):
            raise SpecError(f"org slug {slug!r} is not a lowercase slug")
        orgs.append(
            Org(
                slug=slug,
                name=str(_require(raw, "name", f"org {slug}")),
                description=str(raw.get("description", "")),
                region=raw.get("region"),
                shared=bool(raw.get("shared", False)),
                variables=_str_map(raw.get("variables"), f"org {slug} variables"),
            )
        )
    slugs = [o.slug for o in orgs]
    if len(set(slugs)) != len(slugs):
        raise SpecError("org slugs must be unique")
    if "default" not in slugs:
        raise SpecError("the operator org 'default' is required")
    if sum(o.shared for o in orgs) > 1:
        raise SpecError("at most one org can be shared")

    groups: dict[str, dict[str, str]] = {}
    for group, mapping in _require(spec, "groups", "spec").items():
        if not str(group).startswith("/"):
            raise SpecError(f"group {group!r} must be a full path starting with '/'")
        roles = _str_map(mapping, f"group {group}")
        for org_slug, role in roles.items():
            if org_slug not in slugs:
                raise SpecError(f"group {group}: unknown org {org_slug!r}")
            if role not in ORG_ROLES:
                raise SpecError(f"group {group}: unknown role {role!r}")
        groups[str(group)] = roles

    personas: list[Persona] = []
    for raw in _require(spec, "personas", "spec"):
        username = str(_require(raw, "username", "personas[]"))
        role = str(_require(raw, "role", f"persona {username}"))
        if role not in REALM_ROLES:
            raise SpecError(f"persona {username}: unknown role {role!r}")
        persona_groups = tuple(str(g) for g in raw.get("groups", []))
        for group in persona_groups:
            if group not in groups:
                raise SpecError(f"persona {username}: unknown group {group!r}")
        personas.append(
            Persona(
                username=username,
                persona=str(_require(raw, "persona", f"persona {username}")),
                role=role,
                groups=persona_groups,
                about=str(raw.get("about", "")),
            )
        )
    usernames = [p.username for p in personas]
    if len(set(usernames)) != len(usernames):
        raise SpecError("persona usernames must be unique")

    profiles = {
        str(k): _str_map(v, f"profile {k}") for k, v in _require(spec, "profiles", "spec").items()
    }
    models = _require(spec, "models", "spec")
    for role in models:
        if role not in DEVICE_ROLES:
            raise SpecError(f"models: unknown device role {role!r}")

    sites: list[Site] = []
    for index, raw in enumerate(_require(spec, "sites", "spec"), start=1):
        code = str(_require(raw, "code", "sites[]"))
        if not SITE_CODE.match(code):
            raise SpecError(f"site code {code!r} must be three letters and a digit")
        site = Site(
            code=code,
            name=str(_require(raw, "name", f"site {code}")),
            org=str(_require(raw, "org", f"site {code}")),
            group=str(_require(raw, "group", f"site {code}")),
            status=str(_require(raw, "status", f"site {code}")),
            profile=str(_require(raw, "profile", f"site {code}")),
            source=str(raw.get("source", "bundle")),
            index=index,
        )
        if site.org not in slugs:
            raise SpecError(f"site {code}: unknown org {site.org!r}")
        if site.status not in SITE_STATUSES:
            raise SpecError(f"site {code}: unknown status {site.status!r}")
        if site.profile not in profiles:
            raise SpecError(f"site {code}: unknown profile {site.profile!r}")
        if site.source not in ("bundle", "git"):
            raise SpecError(f"site {code}: source is 'bundle' or 'git'")
        sites.append(site)
    codes = [s.code for s in sites]
    if len(set(codes)) != len(codes):
        raise SpecError("site codes must be unique")

    plan = _require(spec, "ip_plan", "spec")
    try:
        management = ipaddress.IPv4Network(_require(plan, "management", "ip_plan"))
        loopbacks = ipaddress.IPv4Network(_require(plan, "loopbacks", "ip_plan"))
    except ValueError as exc:
        raise SpecError(f"ip_plan: {exc}") from None
    blocks = list(management.subnets(new_prefix=24))

    devices: list[Device] = []
    loopback_hosts = iter(loopbacks.hosts())
    for site in sites:
        block = blocks[site.index]
        hosts = iter(block.hosts())
        for role, count in profiles[site.profile].items():
            if role not in models:
                raise SpecError(f"profile {site.profile}: no model for role {role!r}")
            for number in range(1, int(count) + 1):
                name = f"{site.code}-{role}-{number:02d}"
                hw = models[role]
                devices.append(
                    Device(
                        name=name,
                        site=site.code,
                        org=site.org,
                        role=role,
                        vendor=str(hw["vendor"]),
                        model=str(hw["model"]),
                        platform=str(hw["platform"]),
                        mgmt_host=str(next(hosts)),
                        loopback=str(next(loopback_hosts)),
                        serial=serial_for(name),
                        live=False,
                    )
                )

    devices, lab = _build_lab(spec, devices)

    stories = [
        Story(id=str(raw["id"]), orgs=tuple(str(o) for o in raw.get("orgs", [])))
        for raw in spec.get("stories") or []
    ]
    for story in stories:
        for org_slug in story.orgs:
            if org_slug not in slugs:
                raise SpecError(f"story {story.id}: unknown org {org_slug!r}")

    contacts = {
        str(org_slug): Contact(org=str(org_slug), name=str(c["name"]), mailbox=str(c["email"]))
        for org_slug, c in (spec.get("contacts") or {}).items()
    }

    extra: dict[str, Any] = {}

    catalog = build_catalog(spec.get("service_catalog"), lab.service_prefixes)
    if catalog.enabled and not any(s.source == "git" and s.org == "default" for s in sites):
        # The catalogue rides in the Git inventory the operator's provider reads.
        raise SpecError("service_catalog: enabled needs a site with source: git in org default")

    return Model(
        spec_id=str(spec.get("id", "demo")),
        operator=str(_require(theme, "operator", "theme")),
        domain=str(_require(theme, "domain", "theme")),
        region_root=str(theme.get("region_root", "")),
        orgs=orgs,
        groups=groups,
        personas=personas,
        sites=sites,
        devices=devices,
        stories=stories,
        contacts=contacts,
        lab=lab,
        extra=extra,
        catalog=catalog,
    )


# --------------------------------------------------------------------------- lab

LAB_ROUTER = {"vendor": "FRRouting", "model": "FRR (simulated)", "platform": "ios-xe"}
LAB_SERVER = {"vendor": "Alpine Linux", "model": "Linux server (simulated)", "platform": "linux"}


def _build_lab(spec: dict[str, Any], devices: list[Device]) -> tuple[list[Device], Lab]:
    """Mark the lab's devices live and lay out its networks.

    Every lab router and server keeps its generated inventory record, with the
    management address replaced by its address on the lab's management
    network, which the platform's worker and sandbox join.
    """
    raw = _require(spec, "lab", "spec")
    management = ipaddress.IPv4Network(_require(raw, "management", "lab"))
    mgmt_hosts = list(management.hosts())
    first_host = int(raw.get("first_host", 21))
    pool = list(ipaddress.IPv4Network(_require(raw, "link_pool", "lab")).subnets(new_prefix=29))
    services = ipaddress.IPv4Network(_require(raw, "services", "lab"))
    service_prefixes = ipaddress.IPv4Network(_require(raw, "service_prefixes", "lab"))
    up_raw = _require(raw, "upstream", "lab")
    up_prefix = ipaddress.IPv4Network(_require(up_raw, "prefix", "lab.upstream"))
    asn = int(_require(raw, "asn", "lab"))

    by_name = {d.name: d for d in devices}
    order = [str(n) for n in raw.get("routers", [])] + list(raw.get("servers") or {})
    if len(set(order)) != len(order):
        raise SpecError("lab: a device is listed twice")
    mgmt = iter(mgmt_hosts[first_host - 1 :])
    nodes: list[LabNode] = []
    for name in order:
        if name not in by_name:
            raise SpecError(f"lab: {name} is not a generated device")
        old = by_name[name]
        server = name in (raw.get("servers") or {})
        if server and old.role != "srv":
            raise SpecError(f"lab: server {name} must have the srv role")
        if not server and old.role == "srv":
            raise SpecError(f"lab: router {name} has the srv role")
        lan: tuple[str, ...] = ()
        if server:
            lan = tuple(str(a) for a in raw["servers"][name])
            for address in lan:
                if ipaddress.IPv4Address(address) not in services:
                    raise SpecError(f"lab: {name} address {address} is outside {services}")
        hw = LAB_SERVER if server else LAB_ROUTER
        mgmt_ip = str(next(mgmt))
        by_name[name] = Device(
            name=old.name,
            site=old.site,
            org=old.org,
            role=old.role,
            vendor=hw["vendor"],
            model=hw["model"],
            platform=hw["platform"],
            mgmt_host=mgmt_ip,
            loopback=old.loopback,
            serial=old.serial,
            live=True,
        )
        nodes.append(
            LabNode(
                name=name,
                kind="server" if server else "router",
                org=old.org,
                mgmt_ip=mgmt_ip,
                loopback=None if server else old.loopback,
                asn=None if server else asn,
                lan=lan,
            )
        )
    upstream = LabNode(
        name=str(_require(up_raw, "name", "lab.upstream")),
        kind="router",
        org=None,
        mgmt_ip=str(next(mgmt)),
        loopback=str(up_prefix.network_address + 1),
        asn=int(_require(up_raw, "asn", "lab.upstream")),
    )
    router_names = {n.name for n in nodes if n.kind == "router"} | {upstream.name}

    links: list[Link] = []
    for index, pair in enumerate(raw.get("links") or []):
        a, b = (str(x) for x in pair)
        for end in (a, b):
            if end not in router_names:
                raise SpecError(f"lab link {a}-{b}: {end} is not a lab router")
        if index >= len(pool):
            raise SpecError("lab: link_pool is too small for the links")
        hosts = list(pool[index].hosts())  # .1 is the Docker bridge's gateway
        links.append(
            Link(
                network=f"link-{index + 1:02d}",
                subnet=str(pool[index]),
                a=a,
                a_ip=str(hosts[1]),
                b=b,
                b_ip=str(hosts[2]),
                protocol="ebgp" if upstream.name in (a, b) else "ospf",
            )
        )
    services_router = str(_require(raw, "services_router", "lab"))
    if services_router not in router_names - {upstream.name}:
        raise SpecError(f"lab: services_router {services_router} is not a lab router")
    lab = Lab(
        management=str(management),
        management_network=str(raw.get("management_network", "hegemony-lab-mgmt")),
        asn=asn,
        upstream=upstream,
        upstream_prefix=str(up_prefix),
        services=str(services),
        services_router=services_router,
        services_router_ip=str(list(services.hosts())[-1]),
        service_prefixes=str(service_prefixes),
        nodes=nodes,
        links=links,
    )
    return [by_name[d.name] for d in devices], lab
