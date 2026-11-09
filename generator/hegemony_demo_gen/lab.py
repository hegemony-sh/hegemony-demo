# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The lab: router configurations, its Compose project and its diagrams."""

from __future__ import annotations

import ipaddress
from typing import Any

from .model import Lab, LabNode, Model

# Fixed, published demo credentials. The lab is reachable only on its own
# Docker networks and the host's loopback, never from another machine.
OPERATOR_LOGIN = ("netops", "demo-router-login")
TENANT_LOGIN = ("netops", "demo-device-login")
GIT_LOGIN = ("hegemony", "demo-git-login")
GIT_ORG = "netops"
GIT_INVENTORY_REPO = "inventory"
GIT_BACKUP_REPO = "config-backups"
GIT_HOST = "gitea"
GIT_PORT = 3000

MAILPIT_IMAGE = "axllent/mailpit:v1.31.6"
# Gitea's own registry, so the lab does not add to Docker Hub's anonymous limit.
GITEA_IMAGE = "docker.gitea.com/gitea:1.24.7"

LAB_PROJECT = "hegemony-lab"


def login_for(node: LabNode) -> tuple[str, str]:
    """The SSH login of a lab node: tenants' devices have their own."""
    return OPERATOR_LOGIN if node.org in (None, "default") else TENANT_LOGIN


def git_url(repo: str) -> str:
    """A repository's clone URL as the platform sees it, on the lab's network."""
    return f"http://{GIT_HOST}:{GIT_PORT}/{GIT_ORG}/{repo}.git"


def gitea_ip(lab: Lab) -> str:
    return str(list(ipaddress.IPv4Network(lab.management).hosts())[9])


def mailpit_ip(lab: Lab) -> str:
    return str(list(ipaddress.IPv4Network(lab.management).hosts())[10])


def sandbox_git_url(lab: Lab, repo: str) -> str:
    """The clone URL from inside the sandbox, which has no lab DNS: by address."""
    return f"http://{gitea_ip(lab)}:{GIT_PORT}/{GIT_ORG}/{repo}.git"


# --------------------------------------------------------------------------- FRR


def _upstream_peer_ip(lab: Lab, name: str) -> str | None:
    for link in lab.links_of(name):
        if link.protocol == "ebgp":
            return link.peer(name)[1]
    return None


def frr_config(lab: Lab, node: LabNode) -> str:
    """The FRR configuration of one lab router."""
    lines = [
        "frr defaults traditional",
        f"hostname {node.name}",
        "service integrated-vtysh-config",
        "!",
        "interface lo",
        f" ip address {node.loopback}/32",
        "!",
    ]
    if node is lab.upstream:
        lines += _upstream_config(lab, node)
    else:
        lines += _operator_config(lab, node)
    lines += ["line vty", "!"]
    return "\n".join(lines) + "\n"


def _upstream_config(lab: Lab, node: LabNode) -> list[str]:
    lines = [
        f"ip route {lab.upstream_prefix} Null0",
        "!",
        f"router bgp {node.asn}",
        f" bgp router-id {node.loopback}",
        " no bgp ebgp-requires-policy",
    ]
    peers = [link.peer(node.name) for link in lab.links_of(node.name)]
    for name, address in peers:
        lines += [
            f" neighbor {address} remote-as {lab.asn}",
            f" neighbor {address} description {name}",
        ]
    lines += [" address-family ipv4 unicast", f"  network {lab.upstream_prefix}"]
    lines += [" exit-address-family", "!"]
    return lines


def _operator_config(lab: Lab, node: LabNode) -> list[str]:
    lines: list[str] = []
    ospf_links = [link for link in lab.links_of(node.name) if link.protocol == "ospf"]
    upstream_ip = _upstream_peer_ip(lab, node.name)
    serves_lan = node.name == lab.services_router
    if serves_lan:
        lines += [
            f"ip prefix-list SERVICES-LAN seq 10 permit {lab.services}",
            "route-map SERVICES-LAN permit 10",
            " match ip address prefix-list SERVICES-LAN",
            "!",
        ]
    if upstream_ip:
        aggregate = ipaddress.IPv4Network(f"{node.loopback}/24", strict=False)
        lines += [
            f"ip route {aggregate} Null0",
            f"ip prefix-list TO-UPSTREAM seq 10 permit {aggregate}",
            f"ip prefix-list TO-UPSTREAM seq 20 permit {lab.service_prefixes} le 32",
            f"ip prefix-list TO-UPSTREAM seq 30 permit {lab.services}",
            "route-map TO-UPSTREAM permit 10",
            " match ip address prefix-list TO-UPSTREAM",
            "!",
        ]
    lines += ["router ospf", f" ospf router-id {node.loopback}"]
    lines.append(f" network {node.loopback}/32 area 0")
    lines += [f" network {link.subnet} area 0" for link in ospf_links]
    if serves_lan:
        lines.append(" redistribute connected route-map SERVICES-LAN")
    if upstream_ip:
        # The provider's prefix, so every router can reach "the Internet".
        lines.append(" redistribute bgp")
    lines.append("!")
    if upstream_ip:
        aggregate = ipaddress.IPv4Network(f"{node.loopback}/24", strict=False)
        lines += [
            f"router bgp {lab.asn}",
            f" bgp router-id {node.loopback}",
            " no bgp ebgp-requires-policy",
            f" neighbor {upstream_ip} remote-as {lab.upstream.asn}",
            f" neighbor {upstream_ip} description {lab.upstream.name}",
            " address-family ipv4 unicast",
            f"  network {aggregate}",
            # A service address on this edge itself is a connected route, one
            # on the other edge an OSPF route: export both, filtered.
            "  redistribute connected route-map TO-UPSTREAM",
            "  redistribute ospf route-map TO-UPSTREAM",
            f"  neighbor {upstream_ip} route-map TO-UPSTREAM out",
            " exit-address-family",
            "!",
        ]
    return lines


# --------------------------------------------------------------------------- Compose


def _networks(lab: Lab, node: LabNode) -> dict[str, Any]:
    networks: dict[str, Any] = {"mgmt": {"ipv4_address": node.mgmt_ip}}
    for link in lab.links_of(node.name):
        networks[link.network] = {"ipv4_address": link.address(node.name)}
    if node.name == lab.services_router:
        networks["services"] = {"ipv4_address": lab.services_router_ip}
    if node.lan:
        networks["services"] = {"ipv4_address": _server_lan_ip(lab, node)}
    return networks


def _server_lan_ip(lab: Lab, node: LabNode) -> str:
    """The address Docker gives a server on the services LAN.

    Docker 28 and later drop routed traffic to the addresses they assign
    (only a container on the same network may reach one), so the addresses
    the rest of the lab talks to are the server's own extra addresses, which
    Docker does not know; this one only carries the LAN.
    """
    hosts = list(ipaddress.IPv4Network(lab.services).hosts())
    return str(hosts[199 + lab.servers().index(node)])


def _router_service(lab: Lab, node: LabNode) -> dict[str, Any]:
    _, password = login_for(node)
    return {
        "image": "hegemony-lab-router:local",
        "pull_policy": "build",
        "build": {"context": "../../deploy/lab/router"},
        "hostname": node.name,
        "restart": "unless-stopped",
        "cap_add": ["NET_ADMIN", "NET_RAW", "SYS_ADMIN"],
        "sysctls": {"net.ipv4.ip_forward": 1, "net.ipv4.conf.all.rp_filter": 0},
        # The image's login is `netops`; only the password differs per owner.
        "environment": {"LOGIN_PASSWORD": password},
        "volumes": [f"./frr/{node.name}.conf:/config/frr.conf:ro"],
        "networks": _networks(lab, node),
        "healthcheck": {
            "test": ["CMD-SHELL", "vtysh -c 'show version' >/dev/null && pgrep sshd >/dev/null"],
            "interval": "10s",
            "timeout": "5s",
            "retries": 6,
            "start_period": "20s",
        },
    }


def _server_service(lab: Lab, node: LabNode) -> dict[str, Any]:
    user, password = login_for(node)
    # Reach the routers' loopbacks, the links and the provider through the
    # services router, not through Docker's default gateway.
    routes = sorted(
        {
            str(ipaddress.IPv4Network(f"{lab.upstream.loopback}/24", strict=False)),
            "10.255.0.0/16",
        }
    )
    return {
        "image": "hegemony-lab-server:local",
        "pull_policy": "build",
        "build": {"context": "../../deploy/lab/server"},
        "hostname": node.name,
        "restart": "unless-stopped",
        "cap_add": ["NET_ADMIN"],
        "environment": {
            "LOGIN_USER": user,
            "LOGIN_PASSWORD": password,
            "LAN_ADDRESSES": " ".join(node.lan),
            "LAN_ROUTES": " ".join(routes),
            "LAN_GATEWAY": lab.services_router_ip,
        },
        "networks": _networks(lab, node),
        "healthcheck": {
            "test": ["CMD-SHELL", "pgrep sshd >/dev/null"],
            "interval": "10s",
            "timeout": "5s",
            "retries": 6,
            "start_period": "10s",
        },
    }


def compose(model: Model) -> dict[str, Any]:
    """The lab's Compose project: `docker compose -f dist/lab/compose.yml up -d`."""
    lab = model.lab
    services: dict[str, Any] = {}
    for node in lab.routers():
        services[node.name] = _router_service(lab, node)
    for node in lab.servers():
        services[node.name] = _server_service(lab, node)
    mgmt = ipaddress.IPv4Network(lab.management)
    hosts = list(mgmt.hosts())
    user, password = GIT_LOGIN
    services["gitea"] = {
        "image": GITEA_IMAGE,
        "restart": "unless-stopped",
        "environment": {
            "USER_UID": "1000",
            "USER_GID": "1000",
            "GITEA__database__DB_TYPE": "sqlite3",
            "GITEA__security__INSTALL_LOCK": "true",
            "GITEA__server__ROOT_URL": "http://localhost:${GITEA_UI_PORT:-3000}/",
            "GITEA__server__HTTP_PORT": str(GIT_PORT),
            "GITEA__server__DISABLE_SSH": "true",
            "GITEA__service__DISABLE_REGISTRATION": "true",
            "GITEA__service__REQUIRE_SIGNIN_VIEW": "false",
            "GITEA__repository__DEFAULT_BRANCH": "main",
            "GITEA__log__LEVEL": "Warn",
        },
        "volumes": ["gitea-data:/data"],
        "networks": {"mgmt": {"ipv4_address": gitea_ip(lab), "aliases": [GIT_HOST]}},
        "ports": ["${GITEA_BIND_ADDRESS:-127.0.0.1}:${GITEA_UI_PORT:-3000}:3000"],
        "healthcheck": {
            "test": ["CMD", "curl", "-sf", f"http://localhost:{GIT_PORT}/api/healthz"],
            "interval": "10s",
            "timeout": "5s",
            "retries": 12,
            "start_period": "20s",
        },
    }
    services["gitea-seed"] = {
        "image": GITEA_IMAGE,
        "restart": "no",
        "depends_on": {"gitea": {"condition": "service_healthy"}},
        "user": "1000:1000",
        "entrypoint": ["/bin/sh", "/seed/seed.sh"],
        "environment": {
            "GITEA_URL": f"http://{GIT_HOST}:{GIT_PORT}",
            "GIT_USER": user,
            "GIT_PASSWORD": password,
            "GIT_ORG": GIT_ORG,
            "INVENTORY_REPO": GIT_INVENTORY_REPO,
            "BACKUP_REPO": GIT_BACKUP_REPO,
        },
        "volumes": [
            "gitea-data:/data",
            "../../deploy/lab/gitea/seed.sh:/seed/seed.sh:ro",
            "../inventory:/seed/inventory:ro",
        ],
        "networks": ["mgmt"],
    }
    services["mailpit"] = {
        "image": MAILPIT_IMAGE,
        "restart": "unless-stopped",
        "environment": {
            "MP_SMTP_AUTH_ACCEPT_ANY": "true",
            "MP_SMTP_AUTH_ALLOW_INSECURE": "true",
            "MP_MAX_MESSAGES": "2000",
        },
        "networks": {"mgmt": {"ipv4_address": mailpit_ip(lab), "aliases": ["mailpit"]}},
        "ports": ["${MAILPIT_BIND_ADDRESS:-127.0.0.1}:${MAILPIT_UI_PORT:-8025}:8025"],
    }

    networks: dict[str, Any] = {
        # A fixed name: the platform's api, worker, scheduler and sandbox join it.
        "mgmt": {
            "name": lab.management_network,
            "ipam": {
                "config": [
                    {
                        "subnet": lab.management,
                        "gateway": str(hosts[0]),
                        # Fixed addresses sit below the dynamic range.
                        "ip_range": str(list(mgmt.subnets(new_prefix=mgmt.prefixlen + 1))[1]),
                    }
                ]
            },
        },
        # Not `internal`: Docker filters an internal network's traffic to
        # addresses outside its subnet, which includes routed traffic and
        # OSPF's multicast hellos.
        "services": {"ipam": {"config": [{"subnet": lab.services}]}},
    }
    for link in lab.links:
        networks[link.network] = {"ipam": {"config": [{"subnet": link.subnet}]}}
    return {
        "name": LAB_PROJECT,
        "services": services,
        "networks": networks,
        "volumes": {"gitea-data": {}},
    }


def checks(model: Model, note: str) -> str:
    """The paths deploy/lab/check.sh pings: `service source target` per line.

    Every router reaches the provider from its loopback (OSPF to the edges,
    eBGP beyond), the provider reaches every server address (the edges'
    export), and every server reaches the provider (its routes and source).
    A server's source is `-`: it picks its own.
    """
    lab = model.lab
    up = lab.upstream
    lines = [f"# {note}"]
    for node in lab.routers():
        if node is not up:
            lines.append(f"{node.name} {node.loopback} {up.loopback}")
    for server in lab.servers():
        lines += [f"{up.name} {up.loopback} {address}" for address in server.lan]
        lines.append(f"{server.name} - {up.loopback}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- diagrams


PROTOCOLS = {"ospf": "OSPF", "ebgp": "eBGP"}


def _id(name: str) -> str:
    return name.replace("-", "_")


def _label(model: Model, name: str) -> str:
    lab = model.lab
    node = lab.node(name)
    if node is lab.upstream:
        return f'{_id(name)}(["{name}<br/>upstream provider, AS {node.asn}"])'
    if node.kind == "server":
        return f'{_id(name)}[("{name}<br/>{", ".join(node.lan)}")]'
    return f'{_id(name)}["{name}<br/>{node.loopback}"]'


def mermaid(model: Model, org: str | None = None) -> str:
    """A Mermaid flowchart of the lab, or of the part `org` can see."""
    lab = model.lab
    sites = {s.code: s for s in model.sites}
    visible = {n.name for n in lab.nodes if org is None or n.org == org} | (
        {lab.upstream.name} if org is None else set()
    )
    lines = ["flowchart LR"]
    by_site: dict[str, list[LabNode]] = {}
    for node in lab.nodes:
        if node.name in visible:
            by_site.setdefault(model.device(node.name).site, []).append(node)
    if org is None:
        lines.append(f"  {_label(model, lab.upstream.name)}")
    for code, nodes in by_site.items():
        site = sites[code]
        owner = model.org(site.org).name
        lines.append(f'  subgraph {code}["{site.name} ({owner})"]')
        lines += [f"    {_label(model, n.name)}" for n in nodes]
        lines.append("  end")
    operator = model.org("default").name
    for link in lab.links:
        ends = [end for end in (link.a, link.b) if end in visible]
        if not ends:
            continue
        for end in (link.a, link.b):
            if end not in visible:
                # A tenant sees where its uplink lands, not what lies beyond.
                lines.append(f'  {_id(end)}{{{{"{end}<br/>{operator}"}}}}')
        lines.append(f"  {_id(link.a)} ---|{PROTOCOLS[link.protocol]}| {_id(link.b)}")
    for server in lab.servers():
        if server.name in visible and lab.services_router in visible:
            lines.append(f"  {_id(lab.services_router)} --- {_id(server.name)}")
    return "\n".join(lines) + "\n"


def topology_page(model: Model, note: str) -> str:
    lab = model.lab
    rows = [
        "| Container | Organization | Management | Loopback | Login |",
        "| --- | --- | --- | --- | --- |",
    ]
    names = {o.slug: o.name for o in model.orgs}
    for node in lab.routers() + lab.servers():
        owner = names.get(node.org or "", "none (upstream)")
        loopback = node.loopback or ", ".join(node.lan)
        rows.append(
            f"| `{node.name}` | {owner} | `{node.mgmt_ip}` | `{loopback}` "
            f"| `{login_for(node)[0]}` |"
        )
    links = ["| Link | Network | Ends | Protocol |", "| --- | --- | --- | --- |"]
    for link in lab.links:
        links.append(
            f"| `{link.network}` | `{link.subnet}` | `{link.a}` ({link.a_ip}), "
            f"`{link.b}` ({link.b_ip}) | {PROTOCOLS[link.protocol]} |"
        )
    parts = [
        f"<!-- {note} -->",
        "",
        "# Lab topology",
        "",
        "The lab is its own Compose project, `hegemony-lab`, started before the platform.",
        "The platform's api, worker, scheduler and sandbox join its management network,",
        f"`{lab.management_network}` (`{lab.management}`); nothing else connects the two.",
        "",
        f"Inside, the operator's routers (AS {lab.asn}) run OSPF with each other and the",
        "tenants' routers, and the two edges peer over eBGP with the upstream provider",
        f"(AS {lab.upstream.asn}). The edges announce the loopbacks, the services LAN",
        f"(`{lab.services}`) and anything in `{lab.service_prefixes}` upstream.",
        "",
        "```mermaid",
        mermaid(model).rstrip("\n"),
        "```",
        "",
    ]
    for org in model.orgs:
        if org.slug == "default" or not any(n.org == org.slug for n in lab.nodes):
            continue
        parts += [
            f"## What {org.name} sees",
            "",
            "```mermaid",
            mermaid(model, org.slug).rstrip("\n"),
            "```",
            "",
        ]
    parts += ["## Containers", "", *rows, "", "## Links", "", *links, ""]
    parts += [
        "## Around the network",
        "",
        f"- **Gitea**, <http://localhost:3000>: `{GIT_ORG}/{GIT_INVENTORY_REPO}` holds the",
        "  planned sites the Git inventory provider reads, and",
        f"  `{GIT_ORG}/{GIT_BACKUP_REPO}` the routers' configuration backups.",
        "- **Mailpit**, <http://localhost:8025>: every mail the demo sends.",
        "",
    ]
    return "\n".join(parts)
