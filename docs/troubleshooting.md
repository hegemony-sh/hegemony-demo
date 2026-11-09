<!--
SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>

SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Troubleshooting

Commands below run in the demo directory (`./hegemony-demo/demo`). Without
`task`, use the equivalents in the [README](../README.md#day-to-day).

## The installer stops before it starts

The installer checks the machine first and names what is missing. Run only
the checks with `sh install.sh --preflight`.

| Message | What to do |
| --- | --- |
| `cannot talk to the Docker daemon` | Start Docker. On Linux, add your user to the `docker` group and log in again, or run the installer with `sudo`. |
| `Docker Compose 2.24 or newer is required` | Update Docker Desktop, or install the current `docker-compose-plugin` package. The old `docker-compose` (with a hyphen) is not enough. |
| `Docker has N GiB of memory` | Docker Desktop: Settings > Resources > Memory, 8 GB. On Linux, the machine itself needs it. |
| `only N GiB free for Docker` | Free disk space where Docker keeps images (`docker system df` shows what Docker uses; `docker system prune` removes unused data). |
| `port 8080 is in use` | Stop the program that uses it (`ss -ltnp` or `lsof -iTCP:8080 -sTCP:LISTEN` names it). |
| `pins no platform release yet` | This version of the demo was made before its platform release existed. Use a released demo (`--ref v1.0.0`), or name a platform release with `HEGEMONY_PLATFORM_VERSION`. |

`HEGEMONY_SKIP_RESOURCE_CHECKS=1` skips the memory and disk checks, at your
own risk.

## A check fails at the end of the install

The install ends by checking the demo without running a flow; `task check`
runs the same checks again. Each FAIL line names where to look. A WARN on
ports only says a port answers beyond this machine, which a `*_BIND_ADDRESS`
setting can do on purpose. After a fix, `task check` again; `task up` is
also safe to run again.

## Pulling images fails

- `denied` or `unauthorized` from `ghcr.io`: before the launch the platform
  images are private. Set `HEGEMONY_GHCR_TOKEN` to a token with `read:packages`
  and run again. After the launch no login is needed; if you logged in to
  ghcr.io with an expired token, `docker logout ghcr.io` helps.
- `toomanyrequests` (HTTP 429) from Docker Hub: Docker Hub allows only a few
  anonymous pulls per hour from one address, and the demo pulls about ten of
  its images. Repeated installs, or several machines behind one address, use
  that up. Run `docker login` with a free Docker Hub account (it allows more)
  and run the installer again, or wait an hour.
- Behind a proxy: Docker itself must know the proxy (Docker Desktop: Settings >
  Resources > Proxies; Docker Engine: a systemd drop-in for `docker.service`).

## The API is not ready

The first start imports all demo data and can take a few minutes; the
installer waits up to ten. If it gives up:

```sh
task ps                 # what runs, and what is unhealthy or restarting
task logs -- api        # the API's own account of the import
task logs -- keycloak   # the login server, which the API waits for
```

Keycloak is the slowest to start (often a minute). On a machine with less
than 8 GiB of memory for Docker, containers may be killed: `task ps` then shows
them restarting. `task up` is safe to run again.

## I cannot log in

- The password is `task password`. It is the same for every user.
- The login page is at `localhost:8081` and the UI at `localhost:8080`. Open
  the UI exactly as <http://localhost:8080>; `127.0.0.1:8080` or another name
  breaks the login redirect.
- `admin` is asked to set up a one-time code (any authenticator app works).
  The stories do not need `admin`.
- Five wrong passwords lock a user for a minute or more (brute-force
  protection). Wait, then try again.
- Keycloak reads the users and their password once, when it first starts. If
  you set `HEGEMONY_DEMO_PASSWORD` after that, it has no effect until
  `task reset` and `task up`.

## A story does not work

- **The lab does not converge.** `task lab:check` pings every path the stories
  need and names the ones that do not answer; `task ps` lists the lab's
  containers after the platform's. Look inside a router with
  `deploy/lab/lab.sh exec dlp1-edge-01 vtysh -c 'show ip route'`. The lab uses
  `172.28.103.0/24` (management), `10.255.1.0/24` (links) and `10.90.0.0/24`
  (servers); if one of them is in use on your machine (a VPN, for example),
  change `lab` in `spec/basic.yaml` (then `uv run demo-gen`), and `task reset`
  and `task up`. The map is in [the lab topology](_generated/topology.md).
- **A change is gone.** The routers start from their generated configuration
  every time they start: `task down` and `task up`, or `task lab:reset`, undo
  story 1 and story 2. That is on purpose.
- **No mail.** Everything goes to Mailpit, <http://localhost:8025>, never to a
  real address. Check `task lab:logs -- mailpit`.
- **Standards check fails to start its container.** It runs `alpine:3.22` in
  the platform's sandbox, which pulls it from Docker Hub the first time; that
  needs Internet access from Docker.
- **Olympia has no devices.** The Git inventory provider reads the lab's
  Gitea (`netops/inventory`, <http://localhost:3000>), which the lab seeds at
  every start from the hegemony-demo-inventory tag `platform.env` pins
  (fetched into `deploy/lab/inventory/`). Check `task lab:logs -- gitea-seed`.

## Starting over and removing the demo

```sh
task reset    # delete all demo data; task up starts fresh
```

To remove the demo completely: `task reset`, then delete the install directory.
The images stay in Docker until you remove them (`docker image prune -a`
removes all unused images, not only the demo's).
