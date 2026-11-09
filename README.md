<!--
SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>

SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Hegemony demo

A small, self-contained demo of [Hegemony](https://github.com/hegemony-sh/hegemony),
the network automation platform. One command starts the platform on your
machine next to a small lab: a fictional operator's network of simulated
routers and servers, a Git server and a mail sink. Five short stories show
what Hegemony is for: changes that need a second pair of eyes, long runs that
survive a restart, many customers on one platform, OpenTofu with approvals,
and Ansible backups into Git.

The operator is **Amphictyon Networks**, which runs the network for the
city-states of ancient Greece. It has 4 organizations, 7 users, 6 sites and 15
devices. Its lab runs 6 routers (one of them the upstream provider)
and 2 servers, drawn in [the lab map](docs/_generated/topology.md). All names,
addresses and credentials are made up for the demo.

## Requirements

| | |
| --- | --- |
| System | Linux (x86-64 or arm64), or macOS with Docker Desktop. On Windows, use WSL 2. |
| Docker | Docker Engine or Docker Desktop with the Compose plugin 2.24 or newer |
| Memory | 8 GiB for Docker (6 GiB at least) |
| Disk | 25 GiB free for Docker images and data (15 GiB at least) |
| Tools | `git`, `curl`, `bash`. [`task`](https://taskfile.dev) is optional and makes the lifecycle commands shorter. |
| Ports | 8080, 8081, 8025 and 9000 free on 127.0.0.1 |

The installer checks all of this first and says what is missing.

## Install

```sh
curl -fsSL https://hegemony.sh/install.sh | sh
```

It installs into `./hegemony-demo` (change it with `--dir`), downloads the
images (a few GB, the first time takes several minutes), checks the result
(one PASS or FAIL line per service, the lab network, Gitea, the login server,
the UI and the mail sink, without running a flow), and prints where to log
in. To see the options first: `curl -fsSL https://hegemony.sh/install.sh | sh -s -- --help`.
To only check your machine: `... | sh -s -- --preflight`.

When it is done:

| What | Where |
| --- | --- |
| Hegemony | <http://localhost:8080> |
| Mail sent by the demo | <http://localhost:8025> |
| Password | printed by the installer; later `task password` in the demo directory |

Every user has the same password, generated on your machine. The users are
listed in [the cast](docs/_generated/cast.md): `noc` runs changes, `approver`
approves them, `engineer` builds flows, `auditor` reads everything, and
`athens-admin` and `sparta-admin` each run one customer.

Everything listens on 127.0.0.1 only. The demo is for your own machine: do not
expose it to a network.

## The stories

The [45-minute walkthrough](docs/walkthrough.md) tells all five.

1. **A change with a second pair of eyes.** `noc` asks to advertise a service
   address on two live routers. The run stops until `approver` (and only an
   approver) agrees. Hegemony records the configuration before and after,
   fails the run unless the change really happened, checks that the core
   router learned the route, and mails the result. The audit log says who did
   what.
2. **The run that outlives the worker.** A maintenance window drains the edge
   routers, watches them, and then waits for someone to close the window,
   with a deadline. Restart the workers while it waits for that decision: the
   run carries on where it was, deadline and all.
3. **One standard, many cities.** Athens and Sparta run the one standards
   check the shared standards organization owns. The shared standards apply to both, Athens' own time server wins
   for Athens, each customer's admin sees only their own city, and the
   auditor sees both and can change nothing.
4. **The service as code.** OpenTofu declares which edge routers carry a
   service, and Hegemony keeps the state. The plan compares with that state:
   a new service or a moved address waits for an approver (the flow removes
   the old address), the same values again change nothing, and a router
   changed by hand is found against the state and repaired after approval. A
   second plan finds nothing left, and the upstream provider receives the
   route.
5. **Every change in Git.** An Ansible playbook commits every router's running
   configuration to the lab's Gitea, and only when something changed.

## Day to day

From the demo directory (`./hegemony-demo/demo`; the platform's files are in
`./hegemony-demo/platform`):

| With `task` | Without |
| --- | --- |
| `task up` | `deploy/compose/up.sh` |
| `task down` | `deploy/compose/compose.sh down`, then `deploy/lab/lab.sh down` |
| `task reset` (deletes all demo data) | `deploy/compose/compose.sh down --volumes --remove-orphans`, then `deploy/lab/lab.sh down --volumes --remove-orphans` |
| `task logs -- api` | `deploy/compose/compose.sh logs -f api` |
| `task restart-worker` | `deploy/compose/compose.sh restart worker` |
| `task password` | `grep PASSWORD deploy/compose/.local/demo.env` |
| `task check` (checks only, runs no flow) | `deploy/compose/verify.sh` |

To remove the demo: `task reset`, then delete the directory. Something not
working? See [troubleshooting](docs/troubleshooting.md).

## How it is made

Everything under `dist/` is generated from one small spec,
[`spec/basic.yaml`](spec/basic.yaml), and the story templates under
[`stories/`](stories/), by the generator in `generator/`:

```sh
uv run demo-gen           # write dist/ and docs/_generated/
uv run demo-gen --check   # fail if they are not current
```

The platform version the demo runs is pinned in one file,
[`platform.env`](platform.env), together with the plugin wheels the demo adds;
`python3 scripts/latest_release.py write` moves both to the newest published
platform release. Demo releases are tagged after it: `v1.0.0`
runs platform 1.0.0, and `v1.0.0+demo.2` is a later fix of the demo for the
same platform.

[CONTRIBUTING.md](CONTRIBUTING.md) says how to change the demo. A larger demo
can start from this one with `extends: basic.yaml` in its own spec.

## Licence

AGPL-3.0-or-later. See [LICENSING.md](LICENSING.md).
