<!--
SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>

SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Hegemony demo

[![License: AGPL-3.0-or-later](https://img.shields.io/badge/License-AGPL--3.0--or--later-blue.svg)](LICENSE)
[![Checks](https://github.com/hegemony-sh/hegemony-demo/actions/workflows/check.yml/badge.svg?branch=main&event=push)](https://github.com/hegemony-sh/hegemony-demo/actions/workflows/check.yml)

[Website](https://hegemony.sh/) · [Walkthrough](docs/walkthrough.md) ·
[Lab map](docs/_generated/topology.md) · [Troubleshooting](docs/troubleshooting.md) ·
[Demo inventory](https://github.com/hegemony-sh/hegemony-demo-inventory)

A small, self-contained demo of [Hegemony](https://hegemony.sh/),
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
| Ports | 8080, 8081, 8025, 9000 and 3000 free on 127.0.0.1 |

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
To only check your machine before installing:

```sh
curl -fsSL https://hegemony.sh/install.sh | sh -s -- --preflight
```

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

## Try your first change

Open <http://localhost:8080> and log in as **`noc`** with the generated
password. Follow [A change with a second pair of eyes](docs/walkthrough.md#1-a-change-with-a-second-pair-of-eyes):
start **Announce service prefix**, then approve it as **`approver`** in a
private browser window. Inspect the before-and-after evidence and the result
in Mailpit. The walkthrough includes the exact steps and expected results.

## The stories

The [45-minute walkthrough](docs/walkthrough.md) tells all five.

1. **A change with a second pair of eyes.** Request a router change as `noc`,
   approve it as `approver`, and inspect the evidence and audit trail.
2. **The run that outlives the worker.** Restart workers during a maintenance
   window and see the run resume with its pending decision and deadline intact.
3. **One standard, many cities.** Run shared standards for Athens and Sparta,
   with customer-specific settings and separate access for each city's admin.
4. **The service as code.** Use OpenTofu to plan and approve a service change,
   detect drift, and confirm that a second plan needs no changes.
5. **Every change in Git.** Use Ansible to back up router configurations to
   the lab's Gitea, committing only when something changed.

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
| `task up:local` (platform built from your checkout, see [CONTRIBUTING](CONTRIBUTING.md#run-the-demo-on-an-unreleased-platform-change)) | `HEGEMONY_PLATFORM_BUILD=local deploy/compose/up.sh` |

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

## Versions and related repositories

[`platform.env`](platform.env) pins the platform release, the extra plugin
wheels and the inventory release. Demo releases follow the platform version:
`v1.0.0` runs platform 1.0.0, and `v1.0.0+demo.2` is a later demo fix for the
same platform. These names illustrate the release convention; available
releases are listed on the [Releases page](https://github.com/hegemony-sh/hegemony-demo/releases).

The generator supplies the demo's organizations, users, flows and initial
inventory. The separately versioned
[demo inventory](https://github.com/hegemony-sh/hegemony-demo-inventory)
supplies Olympia's planned devices and the service catalogue. The lab copies
that pinned inventory into Gitea, and the Git inventory provider syncs it
into Hegemony. A change to that repository's `main` does not change an
already pinned demo.

See [Contributing](CONTRIBUTING.md) for generator development and
[Releasing](CONTRIBUTING.md#releasing) for updating the pins. A larger demo
can start from this one with `extends: basic.yaml` in its own spec.

## Contributing, security and licence

- Report installation problems and request improvements through
  [GitHub Issues](https://github.com/hegemony-sh/hegemony-demo/issues).
- Read [Contributing](CONTRIBUTING.md) before opening a pull request. Commits
  follow Conventional Commits and require a DCO sign-off (`git commit -s`).
- Report vulnerabilities privately as described in [Security](SECURITY.md).
- Participation follows the [Code of Conduct](CODE_OF_CONDUCT.md).
- Licensed under `AGPL-3.0-or-later`; see [Licensing](LICENSING.md).

The [Checks workflow](https://github.com/hegemony-sh/hegemony-demo/actions/workflows/check.yml)
validates the source, generated data, pinned inventory and REUSE licensing
metadata. The [Scorecard workflow](https://github.com/hegemony-sh/hegemony-demo/actions/workflows/scorecard.yml)
checks repository and supply-chain practices after changes to `main` and
weekly. Its findings appear in the repository's code-scanning results;
they are not a security certification of the running demo.
