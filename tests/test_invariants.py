# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Schema, reference and consistency checks on the committed generated files.

The section and field lists mirror the platform's Configuration Exchange
models (schema 3: apps/api/schemas_config_exchange.py in the platform
repository). A bundle with an unknown field is refused at import, so these
fail here first. The end-to-end workflow imports the bundles into a real API.
"""

from __future__ import annotations

import ipaddress
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import yaml
from hegemony_demo_gen.model import Model, build_model
from hegemony_demo_gen.spec import load_spec

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"

SECTION_FIELDS: dict[str, set[str]] = {
    "organizations": {
        "slug", "name", "description", "is_active", "is_shared", "members", "idp_mappings",
    },
    "secrets": {
        "name", "description", "backend_ref", "backend_scheme", "backend_name", "folder", "values",
    },
    "sites": {"name", "description", "location", "tags", "parent"},
    "devices": {
        "attributes", "mgmt_ips", "name", "hostname", "mgmt_host", "mgmt_port", "site",
        "access_config", "platform", "tags",
    },
    "flows": {
        "name", "description", "tags", "pinned", "manual_runs_enabled", "definition",
        "git_repository", "git_path", "git_branch", "sync_mode", "auto_commit", "notifications",
    },
    "flow_attachments": {"flow", "filename", "content", "git_repository", "git_file_path"},
    "notification_destinations": {"name", "type", "enabled", "config_json"},
    "flow_subscriptions": {"flow", "destination", "event", "enabled", "filters_json"},
    "variables": {"name", "value", "description"},
    "schedules": {
        "name", "flow", "schedule_type", "run_at", "cron_expression", "interval_seconds",
        "timezone", "related_targets", "params", "enabled",
    },
    "git_repositories": {
        "name", "url", "branch", "auth_secret_ref", "ssh_key_secret_ref", "sync_stale_seconds",
        "allow_insecure_url",
    },
    "inventory_providers": {
        "name", "provider_type", "enabled", "description", "config", "sync_interval_seconds",
        "delta_sync_enabled", "full_reconcile_interval_seconds", "step_sync_enabled",
        "object_types",
    },
}  # fmt: skip
ENVELOPE = {"schema_version", "organization", *SECTION_FIELDS}
ORG_ROLES = {"admin", "editor", "operator", "approver", "auditor", "viewer"}
EVENTS = {
    "run.started", "run.paused", "run.resumed", "run.cancelled", "run.failed", "run.completed",
    "approval.requested", "approval.approved", "approval.rejected", "approval.expired",
}  # fmt: skip
# Step handlers the platform 1.0.0 images ship (hegemony-step-plugins 0.33).
HANDLERS = {
    "ansible.playbook", "container.run", "evidence.assert", "evidence.compare", "flow.notify",
    "flow.run", "tf.apply", "tf.plan",
    "general.noop", "general.sleep", "inventory.sync", "monitor.connectivity",
    "netcli.collect_evidence", "netcli.execute", "probe.connectivity", "probe.dns",
    "probe.http", "probe.tls", "probe.wait_reachable", "secret.write", "shell.execute",
}  # fmt: skip
NODE_PORTS = {
    "start": {"start"},
    "step": {"success", "failure"},
    "approval": {"approved", "rejected", "expired"},
}
SECRET_REF = re.compile(r"vault://orgs/([a-z0-9-]+)/secrets/([\w/-]+)/(\w+)'")


def model() -> Model:
    return build_model(load_spec(ROOT / "spec" / "basic.yaml"))


def bundles() -> dict[str, dict[str, Any]]:
    return {
        p.name: yaml.safe_load(p.read_text()) for p in sorted((DIST / "bundles").glob("*.yaml"))
    }


ORG_BUNDLES = {k: v for k, v in bundles().items() if "organization" in v}


def test_bundle_files_are_ordered_directory_first() -> None:
    names = list(bundles())
    assert names[0] == "00-organizations.yaml"
    assert names == sorted(names)


@pytest.mark.parametrize("name", list(bundles()))
def test_bundles_use_only_known_sections_and_fields(name: str) -> None:
    bundle = bundles()[name]
    assert bundle["schema_version"] == 3
    assert set(bundle) <= ENVELOPE, set(bundle) - ENVELOPE
    for section, items in bundle.items():
        if section in SECTION_FIELDS:
            for item in items:
                assert set(item) <= SECTION_FIELDS[section], (
                    section,
                    set(item) - SECTION_FIELDS[section],
                )


def test_every_org_bundle_names_an_org_of_the_directory() -> None:
    directory = bundles()["00-organizations.yaml"]["organizations"]
    slugs = [o["slug"] for o in directory]
    assert sorted(b["organization"] for b in ORG_BUNDLES.values()) == sorted(slugs)
    for org in directory:
        for mapping in org["idp_mappings"]:
            assert mapping["role"] in ORG_ROLES
            assert mapping["claim"] == "groups"


@pytest.mark.parametrize("name", list(ORG_BUNDLES))
def test_references_inside_an_org_bundle_resolve(name: str) -> None:
    bundle = ORG_BUNDLES[name]
    org = bundle["organization"]
    flows = {f["name"] for f in bundle.get("flows", [])}
    destinations = {d["name"] for d in bundle.get("notification_destinations", [])}
    sites = {s["name"] for s in bundle.get("sites", [])}
    devices = {d["name"] for d in bundle.get("devices", [])}
    secrets = {
        (s["folder"].removeprefix(f"orgs/{org}/secrets/"), key)
        for s in bundle.get("secrets", [])
        for key in s["values"]
    }
    repositories = {r["name"] for r in bundle.get("git_repositories", [])}

    for sub in bundle.get("flow_subscriptions", []):
        assert sub["flow"] in flows and sub["destination"] in destinations, sub
        assert sub["event"] in EVENTS
    for item in bundle.get("flow_attachments", []) + bundle.get("schedules", []):
        assert item["flow"] in flows
    for device in bundle.get("devices", []):
        assert device["site"] in sites
    for provider in bundle.get("inventory_providers", []):
        if provider["provider_type"] == "git":
            assert provider["config"]["git_repository"] in repositories
    for match in SECRET_REF.finditer(yaml.safe_dump(bundle)):
        assert match.group(1) == org, "a secret reference crosses organizations"
        assert (match.group(2), match.group(3)) in secrets, match.group(0)
    for flow in bundle.get("flows", []):
        for field in flow["definition"].get("form", {}).get("nodes", []):
            if field["data"].get("field_type") == "inventory.device":
                for default in field["data"].get("default_value", []):
                    assert default in devices, (flow["name"], default)


@pytest.mark.parametrize(
    "flow", [f for b in ORG_BUNDLES.values() for f in b.get("flows", [])], ids=lambda f: f["name"]
)
def test_flow_graphs_are_wired(flow: dict[str, Any]) -> None:
    graph = flow["definition"]["graph"]
    nodes = {n["id"]: n for n in graph["nodes"]}
    assert len(nodes) == len(graph["nodes"]), "duplicate node ids"
    roles = {
        f["data"]["config"]["role"]
        for f in flow["definition"].get("form", {}).get("nodes", [])
        if f["data"].get("field_type") == "inventory.device"
    }
    for node in nodes.values():
        if node["type"] == "step":
            assert node["handler"] in HANDLERS, node["handler"]
        for selector in node.get("target_selectors", []):
            if selector["type"] == "role":
                assert selector["role"] in roles, (node["id"], selector["role"])
    for edge in graph["edges"]:
        source, _, port = edge["source"].partition(":")
        assert source in nodes and edge["target"] in nodes, edge
        assert port in NODE_PORTS.get(nodes[source]["type"], {port}), edge
    reached = {e["target"] for e in graph["edges"]}
    assert set(nodes) - reached == {"start"}, "every node but start has an incoming edge"


def test_devices_are_unique_with_unique_addresses() -> None:
    m = model()
    names = Counter(d.name for d in m.devices)
    assert max(names.values()) == 1
    for field in ("mgmt_host", "loopback"):
        values = Counter(getattr(d, field) for d in m.devices)
        assert max(values.values()) == 1, field


def test_addresses_sit_inside_their_plan() -> None:
    m = model()
    spec = load_spec(ROOT / "spec" / "basic.yaml")
    management = ipaddress.ip_network(spec["ip_plan"]["management"])
    loopbacks = ipaddress.ip_network(spec["ip_plan"]["loopbacks"])
    live = ipaddress.ip_network(m.lab.management)
    for device in m.devices:
        net = live if device.live else management
        assert ipaddress.ip_address(device.mgmt_host) in net, device.name
        assert ipaddress.ip_address(device.loopback) in loopbacks, device.name
    pool = ipaddress.IPv4Network(spec["lab"]["link_pool"])
    for link in m.lab.links:
        subnet = ipaddress.IPv4Network(link.subnet)
        assert subnet.subnet_of(pool)
        assert {ipaddress.ip_address(link.a_ip), ipaddress.ip_address(link.b_ip)} <= set(
            subnet.hosts()
        )


def test_a_device_belongs_to_its_site_org() -> None:
    m = model()
    site_org = {s.code: s.org for s in m.sites}
    for device in m.devices:
        assert device.org == site_org[device.site]
        assert device.name.startswith(device.site + "-")


def test_lab_addresses_sit_below_the_dynamic_range() -> None:
    lab = model().lab
    compose = yaml.safe_load((DIST / "lab/compose.yml").read_text())
    ipam = compose["networks"]["mgmt"]["ipam"]["config"][0]
    subnet = ipaddress.ip_network(ipam["subnet"])
    dynamic = ipaddress.ip_network(ipam["ip_range"])
    fixed: list[str] = []
    for service in compose["services"].values():
        mgmt = service.get("networks") or {}
        if isinstance(mgmt, dict) and (mgmt.get("mgmt") or {}).get("ipv4_address"):
            fixed.append(mgmt["mgmt"]["ipv4_address"])
    assert len(set(fixed)) == len(fixed)
    assert {n.mgmt_ip for n in lab.routers() + lab.servers()} <= set(fixed)
    for address in map(ipaddress.ip_address, fixed):
        assert address in subnet and address not in dynamic
        assert str(address) != ipam["gateway"]


def test_the_lab_does_not_overlap_the_platform_network() -> None:
    env = dict(
        line.split("=", 1)
        for line in (ROOT / "deploy/compose/.env.demo").read_text().splitlines()
        if "=" in line and not line.startswith("#")
    )
    platform = ipaddress.ip_network(env["HEGEMONY_COMPOSE_SUBNET"])
    compose = yaml.safe_load((DIST / "lab/compose.yml").read_text())
    for network in compose["networks"].values():
        subnet = ipaddress.ip_network(network["ipam"]["config"][0]["subnet"])
        assert not subnet.overlaps(platform), subnet


def test_the_platform_joins_the_lab_network_by_name() -> None:
    demo = yaml.safe_load((ROOT / "deploy/compose/docker-compose.demo.yml").read_text())
    assert demo["networks"]["lab"] == {"name": model().lab.management_network, "external": True}
    for service in ("api", "worker", "dind"):
        assert "lab" in demo["services"][service]["networks"], service


def test_each_persona_reaches_exactly_the_orgs_the_cast_table_shows() -> None:
    m = model()
    cast = (ROOT / "docs/_generated/cast.md").read_text()
    names = {o.slug: o.name for o in m.orgs}
    for persona in m.personas:
        row = next(line for line in cast.splitlines() if line.startswith(f"| `{persona.username}`"))
        reach = {s for g in persona.groups for s in m.groups[g]}
        for slug, name in names.items():
            assert (f"{name} (" in row) == (slug in reach), (persona.username, slug)


def test_tenant_admins_reach_only_their_tenant_and_the_shared_org() -> None:
    m = model()
    for persona in m.personas:
        if not persona.username.endswith("-admin"):
            continue
        tenant = persona.username.removesuffix("-admin")
        reach = {s for g in persona.groups for s in m.groups[g]}
        assert reach == {tenant, "shared"}
        assert all(m.groups[g].get("shared") == "viewer" for g in persona.groups)


def test_the_auditor_reads_everything_and_can_change_nothing() -> None:
    m = model()
    auditor = next(p for p in m.personas if p.username == "auditor")
    roles = {r for g in auditor.groups for r in m.groups[g].values()}
    reach = {s for g in auditor.groups for s in m.groups[g]}
    assert auditor.role == "auditor" and roles == {"auditor"}
    assert reach == {o.slug for o in m.orgs}


def test_the_operator_cannot_approve_and_the_approver_cannot_run() -> None:
    m = model()
    by_name = {p.username: p for p in m.personas}
    noc = {r for g in by_name["noc"].groups for r in m.groups[g].values()}
    approver = {r for g in by_name["approver"].groups for r in m.groups[g].values()}
    assert "approver" not in noc and "admin" not in noc
    assert approver <= {"approver", "viewer"}


class TestKeycloakRealm:
    realm: dict[str, Any] = json.loads((DIST / "keycloak/realm.json").read_text())

    def test_no_password_is_stored(self) -> None:
        for user in self.realm["users"]:
            assert [c["value"] for c in user["credentials"]] == ["${HEGEMONY_DEMO_PASSWORD}"]
            assert all(c["temporary"] is False for c in user["credentials"])

    def test_clients_are_locked_down(self) -> None:
        for client in self.realm["clients"]:
            assert client.get("directAccessGrantsEnabled") is False, client["clientId"]
            assert not client.get("implicitFlowEnabled"), client["clientId"]
            assert "secret" not in client, client["clientId"]
            for uri in client.get("redirectUris", []) + client.get("webOrigins", []):
                assert uri.startswith("http://localhost:"), uri
        ui = next(c for c in self.realm["clients"] if c["clientId"] == "hegemony-ui")
        assert ui["publicClient"] is True
        assert ui["attributes"]["pkce.code.challenge.method"] == "S256"

    def test_user_names_pass_keycloaks_profile_check(self) -> None:
        # Keycloak 26's person-name-prohibited-characters validator. A name it
        # refuses leaves the account "not fully set up", so no one can log in.
        allowed = re.compile(r"^[^<>&\"\v$%!#?§;*~/\\|^=\[\]{}()\x00-\x1f\x7f]+$")
        for user in self.realm["users"]:
            for field in ("firstName", "lastName"):
                assert allowed.match(user[field]), (user["username"], field, user[field])

    def test_realm_defaults_are_safe(self) -> None:
        assert self.realm["bruteForceProtected"] is True
        assert self.realm["registrationAllowed"] is False
        assert self.realm["sslRequired"] == "external"
        assert "length(12)" in self.realm["passwordPolicy"]

    def test_users_and_groups_match_the_spec_and_the_overlay(self) -> None:
        m = model()
        assert [u["username"] for u in self.realm["users"]] == [p.username for p in m.personas]
        groups = {g["path"] for g in self.realm["groups"]}
        assert groups == set(m.groups)
        for user in self.realm["users"]:
            assert set(user["groups"]) <= groups
        env = (DIST / "demo.env").read_text()
        users = " ".join(p.username for p in m.personas)
        assert f'KEYCLOAK_IMPORTED_USERS="{users}"' in env


def test_each_lab_login_matches_its_owners_secret() -> None:
    compose = yaml.safe_load((DIST / "lab/compose.yml").read_text())
    secrets = {}
    for bundle in ORG_BUNDLES.values():
        for secret in bundle.get("secrets", []):
            if secret["name"].endswith("device-ssh"):
                secrets[bundle["organization"]] = secret["values"]["password"]
    for node in model().lab.routers() + model().lab.servers():
        if node.org is None:
            continue
        password = compose["services"][node.name]["environment"]["LOGIN_PASSWORD"]
        assert password == secrets[node.org], node.name


def test_published_ports_bind_loopback_only() -> None:
    overlays = [*(ROOT / "deploy/compose").glob("docker-compose.*.yml"), DIST / "lab/compose.yml"]
    for overlay in overlays:
        services = yaml.safe_load(overlay.read_text()).get("services", {})
        for name, service in services.items():
            for port in service.get("ports", []):
                assert str(port).startswith(
                    ("${MAILPIT_BIND_ADDRESS:-127.0.0.1}:", "${GITEA_BIND_ADDRESS:-127.0.0.1}:")
                ) or str(port).startswith("127.0.0.1:"), (overlay.name, name, port)


def test_summary_counts_match_the_spec() -> None:
    m = model()
    summary = json.loads((DIST / "summary.json").read_text())
    assert summary["organizations"] == len(m.orgs) == 4
    assert summary["users"] == len(m.personas) == 7
    assert summary["live_devices"] == 7
    assert summary["lab_routers"] == 6
    assert summary["lab_servers"] == 2
    assert summary["sites"] == len(m.sites)
    assert summary["devices"] == len(m.devices)


def test_manifest_lists_every_dist_file_with_its_digest() -> None:
    import hashlib

    manifest = json.loads((DIST / "MANIFEST.json").read_text())["files"]
    on_disk = {
        p.relative_to(ROOT).as_posix()
        for p in DIST.rglob("*")
        if p.is_file() and p.name != "MANIFEST.json"
    }
    assert set(manifest) == on_disk
    for path, digest in manifest.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest


def test_only_the_admin_persona_holds_a_realm_role_beyond_the_default() -> None:
    realm = json.loads((DIST / "keycloak/realm.json").read_text())
    for user in realm["users"]:
        expected = (
            ["admin", "default-roles-hegemony"]
            if user["username"] == "admin"
            else ["default-roles-hegemony"]
        )
        assert user["realmRoles"] == expected, user["username"]


def test_the_standards_flow_is_one_flow_in_the_active_shared_org() -> None:
    directory = bundles()["00-organizations.yaml"]["organizations"]
    shared = [o for o in directory if o.get("is_shared")]
    assert len(shared) == 1 and shared[0]["is_active"] is True
    owners = [
        b["organization"]
        for b in ORG_BUNDLES.values()
        for f in b.get("flows", [])
        if f["name"] == "Standards check"
    ]
    assert owners == [shared[0]["slug"]]
