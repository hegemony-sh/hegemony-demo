<!--
SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>

SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Security Policy

Security reports are handled privately. Please do not open a public GitHub issue
for vulnerabilities, suspected vulnerabilities, leaked secrets, or exploit
details.

This repository holds the public demo of
[Hegemony](https://github.com/hegemony-sh/hegemony): the demo data and its
generator, the one-command installer (`install.sh`) and the Compose overlay that
runs the demo. Vulnerabilities in the platform itself are reported the same way,
to the same address; see the platform's
[Security Policy](https://github.com/hegemony-sh/hegemony/blob/develop/SECURITY.md).

## Supported versions

Demo releases are tagged after the platform release they target: `v1.0.0` runs
platform 1.0.0, and `v1.0.0+demo.2` is a later demo-only fix for the same
platform release. Releases are immutable, so a fix ships as a new release, and
only the newest release receives fixes.

## Reporting a vulnerability

Report vulnerabilities privately by emailing
[security@hegemony.sh](mailto:security@hegemony.sh).

Please include as much detail as you can safely share: the affected part (the
installer, a file under `dist/`, the Compose overlay, a workflow), the release
tag or commit, the impact, reproduction steps, and a safe way to contact you.
Do not include real credentials, private keys or customer data in a report.

## What is in scope

- The installer and the release assets, for example an `install.sh` that runs
  or downloads something other than what it says, or a released asset that does
  not match its `SHA256SUMS` entry.
- The demo stack's configuration, for example a port that binds beyond
  loopback, or a script that writes a password or token to a log.
- The release and CI workflows of this repository.

The demo's fixed credentials are not secret: the simulated routers' SSH login
and the service passwords in `deploy/compose/.env.demo` are published demo
values, and the routers are reachable only on the demo's internal network. The
users' login password is generated on your machine at install time and kept in
`deploy/compose/.local/` (mode 600). The demo is meant to run on the machine you
drive it from; do not expose it to a network you do not control. A real
credential committed by mistake is in scope.

## Response targets

| Stage | Target |
| --- | --- |
| Acknowledge receipt | 48 hours |
| Initial triage and severity assessment | 7 days |
| Coordinated fix and disclosure target | 90 days |

## Safe harbor

Security research conducted in good faith is welcome. Please avoid privacy
violations, service disruption, data destruction, persistence, social
engineering, spam, and testing against systems you do not own or do not have
permission to test.
