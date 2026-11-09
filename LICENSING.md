<!--
SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>

SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Licensing

The source code in this repository is licensed under `AGPL-3.0-or-later`,
and under no other licence. See [LICENSE](LICENSE) and
[LICENSES/AGPL-3.0-or-later.txt](LICENSES/AGPL-3.0-or-later.txt).

Rexonix s.r.o. is the copyright holder of the project's own files, and Jakub
Trávník is their author. Each first-party file that carries an SPDX header says
so in REUSE form: `SPDX-FileCopyrightText` names Rexonix s.r.o. and
`SPDX-FileContributor` names Jakub Trávník. Files without a header, such as
`uv.lock`, JSON files and the generated router configurations, are annotated in
[REUSE.toml](REUSE.toml), which names the holder only.

Contributions are accepted under the same licence, with a
[Developer Certificate of Origin](https://developercertificate.org/) sign-off
on every commit; there is no Contributor License Agreement. A contributor who
does not write on behalf of Rexonix s.r.o. keeps the copyright in their
contribution. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Names in the demo data

The demo's operator, cities and people take their names from ancient Greek
geography and mythology, which are in the public domain. "Amphictyon Networks"
is a fictional company. Mail and web addresses use `amphictyon.example`, a
domain reserved for documentation (RFC 2606), so none of them resolves.
Addresses are private (RFC 1918) or documentation (RFC 5737) ranges. Device
records name real vendor models only to look like a real inventory; no vendor
endorses or is affiliated with this demo.

## Code of Conduct

[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) adapts Contributor Covenant 2.1 by
Coraline Ada Ehmke and its contributors. That document retains **CC-BY-4.0**,
with upstream attribution and local changes recorded in the file. Its license
text is in [LICENSES/CC-BY-4.0.txt](LICENSES/CC-BY-4.0.txt).

## Third-party services

The demo starts the platform's own services (see the platform's
[THIRD-PARTY-NOTICES.md](https://github.com/hegemony-sh/hegemony/blob/develop/THIRD-PARTY-NOTICES.md))
and adds the ones below from this repository's Compose overlay and lab. This
repository does not redistribute any of them: the Compose files name an image
tag and your container runtime pulls it. Their licenses bind whoever runs them.

| Service | Image | License |
| --- | --- | --- |
| Mailpit, the mail sink | `axllent/mailpit` | MIT |
| FRRouting, the simulated routers | `quay.io/frrouting/frr` | GPL-2.0-or-later, on an Alpine userland |
| Alpine Linux, the simulated servers | `public.ecr.aws/docker/library/alpine` | Alpine's packages, each under its own licence |
| OpenSSH, Python and sudo, inside the simulated routers and servers | Alpine packages | BSD-style (OpenSSH), PSF-2.0, ISC-style (sudo) |
| Gitea, the lab's Git server | `docker.gitea.com/gitea` | MIT |

If you redistribute a demo deployment, as an image bundle or an appliance, you
become a distributor of these services and take on their terms directly.
