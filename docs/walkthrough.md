<!--
SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>

SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Walkthrough: 45 minutes

Five stories, told by the people of Amphictyon Networks, the operator that
runs the network for the city-states. You need the demo running (see the
[README](../README.md)) and two browser windows: one normal, one private, so
you can be two people at once.

| Time | Part |
| --- | --- |
| 3 min | [0. Find your way](#0-find-your-way) |
| 10 min | [1. A change with a second pair of eyes](#1-a-change-with-a-second-pair-of-eyes) |
| 9 min | [2. The run that outlives the worker](#2-the-run-that-outlives-the-worker) |
| 8 min | [3. One standard, many cities](#3-one-standard-many-cities) |
| 8 min | [4. The service as code](#4-the-service-as-code) |
| 6 min | [5. Every change in Git](#5-every-change-in-git) |

## 0. Find your way

Open <http://localhost:8080>, <http://localhost:8025> (Mailpit, where every
mail the demo sends arrives) and <http://localhost:3000> (Gitea, the lab's Git
server). Get the password with `task password` in the demo directory.

The network the stories change is a small lab next to the platform, drawn in
[docs/_generated/topology.md](_generated/topology.md): the operator's routers in
Delphi, one router each for Athens and Sparta, two servers, and an upstream
provider the Delphi edges peer with over eBGP.

Every story names the login to use, which is also the name the app shows at
the top. In short: `noc` runs changes, `approver` approves them, `engineer`
builds flows, `auditor` reads everything, and `athens-admin` and
`sparta-admin` each run one city. `admin` runs the platform; the stories do not
need it, and as an administrator it is asked to set up a one-time code at its
first login. Each login also has a character from Greek myth, listed in
[docs/_generated/cast.md](_generated/cast.md) with its organizations and
roles.

Log in as **`engineer`** and look around:

- **Organizations**: the switcher at the top lists Amphictyon Networks (the
  operator), Oracle of Delphi (the shared standards), Athens and Sparta.
- **Inventory**: the operator's site Delphi has six devices. Five run in the
  lab: three routers (FRR, the open source routing suite; their model says
  *FRR (simulated)*) and two Linux servers. The planned site Olympia comes
  from a second source: the Git inventory provider reads it from the lab's
  Gitea, repository `netops/inventory`. The sites table is in
  [docs/_generated/sites.md](_generated/sites.md).
- **Flows**: *Announce service prefix*, *Maintenance window*, *Service as
  code* and *Configuration backup*. Open one in the editor to see the graph
  the stories run.
- **Plugins**: the step, inventory and notification plugins the platform runs,
  among them the Git inventory plugin the demo adds.

Log out.

## 1. A change with a second pair of eyes

*`noc` watches the network. A customer needs a new service address announced
from the Delphi edge routers. `noc` may ask for the change, but not let it
through alone.*

1. In the normal window, log in as **`noc`**. Open the flow
   **Announce service prefix** and start a run. The form comes filled in: the
   two edge routers `dlp1-edge-01` and `dlp1-edge-02`, the core router
   `dlp1-core-01` that should learn the route, the address `10.255.100.1` and
   the change reference `CHG-1001`. Start it.
2. The run stops at **Approve the change**. `noc` has no way to approve it:
   operators run flows, approvers approve them, and nobody does both.
3. In Mailpit, a mail to `approvals@amphictyon.example` says an approval is
   waiting.
4. In the private window, log in as **`approver`**. Open the pending approval
   (from the approvals list, or the link in the mail) and approve it.
   `approver` can approve, but cannot start or edit flows.
5. Back in the `noc` window, watch the run:
   - **Evidence before** saves each edge router's running configuration and
     OSPF routes.
   - **Apply the change** adds the address to the loopback and to OSPF.
   - **Evidence after** saves them again, and **The configuration changed**
     compares the two. A detected difference continues to the core check;
     the comparison's failure path ends at **No change detected**, a success
     terminal. Open the step to inspect the diff or any comparison error.
   - **The core learned the route** asks `dlp1-core-01` for the new route; its
     output shows the route learned over OSPF from the edge routers.
6. Mailpit has the result for `noc@amphictyon.example`.
7. In the private window, log out and log in as **`auditor`**. The audit log
   shows the run started by `noc` and the approval by `approver`, with times.
   `auditor` can open everything, including the evidence, and change nothing.

Try it again with a different address and reject it as `approver`: the run
ends at **Unexpected failure** and nothing touches the routers. A second run
started while one is going, or within a minute after it, is held back: the
flow allows one run at a time, with a cooldown, because it changes live
routers.

## 2. The run that outlives the worker

*A maintenance window on the Delphi edge routers. In real life it lasts hours,
and the machines that run it may be restarted in the meantime. Hegemony keeps
the state of every run in its workflow engine, not in the worker that happens
to execute it.*

1. As **`noc`**, start **Maintenance window** with its defaults (the two edge
   routers).
2. The run drains the routers (**Drain the edge routers** sets OSPF max-metric,
   so traffic avoids them), **Let traffic settle** pauses for half a minute,
   then a **Fork** starts **Watch reachability** and **Close the window** in
   parallel. The monitor samples the routers' SSH port every five seconds
   while the window is open and draws the result live.
3. The run waits at **Close the window**, an approval with a deadline of 15
   minutes, while monitoring continues. Now restart the workers from the demo
   directory:

   ```sh
   task restart-worker          # or: deploy/compose/compose.sh restart worker
   ```

4. Refresh the run. It is still there, still waiting at the approval, and the
   deadline still counts down: the wait and its timer live in the workflow
   engine, not in a worker. Restart them as often as you like.
5. As **`approver`**, approve it. **Restore the edge routers** removes
   max-metric and **Evidence after the window** records the result. If nobody
   decides within 15 minutes, the window closes itself the same way, and the
   NOC mailbox gets a mail saying the approval expired.

Also worth a look: **Schedules** has a *Weekly maintenance window* for Sunday
03:00 UTC. It ships disabled, so the demo never drains routers on its own.

## 3. One standard, many cities

*The Oracle of Delphi sets the standards every city follows: time, name and
log servers. Athens runs its own time server; Sparta takes the standards as
they are. Each city's admin sees their own city only.*

1. Log in as **`athens-admin`**. The organization switcher shows Athens and the
   Oracle of Delphi, and nothing of Sparta or of the operator.
2. In Athens, run **Standards check**. The flow belongs to the Oracle of
   Delphi and there is only one copy of it; Athens runs it as its own (city
   admins hold the operator rights in their city). Its report (the step's output and its artifact
   `standards.txt`) says:
   - NTP primary `10.92.0.123`: Athens' own setting wins;
   - DNS and syslog from the shared standards, `10.90.0.53` and `10.90.0.14`.
3. Open **Variables** in the Oracle of Delphi: `athens-admin` can read the shared
   standards and the flow but not change them.
4. Log in as **`sparta-admin`** in the private window and run the same flow in
   Sparta: NTP primary is the shared `10.90.0.123`. `sparta-admin` cannot see
   Athens.
5. Log in as **`auditor`**: it sees both cities' runs and reports and can
   start none of them.

Both cities run the one shared flow. What differs is each city's variables,
which win over the shared ones, and who may see the results.

## 4. The service as code

*The operator declares its services in OpenTofu (the open source fork of
Terraform), and Hegemony keeps the state. FRR has no OpenTofu provider, so
OpenTofu decides and Hegemony writes what it decided to the routers.*

1. As **`noc`**, open **Service as code** and run it with the defaults: service
   `portal` on `10.255.100.20`, on both Delphi edges.
2. **What the routers carry** reads each edge's loopback as JSON and hands it
   to **Plan**, where OpenTofu checks that no router already uses the address
   for something else. The plan compares the declaration with the state
   Hegemony keeps for `edge-services`, and the run waits at **Approve the
   plan**, whose title carries the plan's summary (*Plan: +2 ~0 -0*): one
   resource to add per edge router.
3. As **`approver`**, open the approval and read the plan in the plan step's
   artifacts. Approve it.
4. **Apply** applies exactly that plan and stores the new state (under
   **Terraform States**, versioned and locked). **Push to the routers** writes
   what the apply produced (its `address` and `description` outputs) to both
   edges.
5. **What the routers carry now** reads them again, **Plan again** finds
   nothing left to change, and **Announced upstream?** checks that each edge
   sends the route on to the provider: FRR's view of the route lists the peers
   it is advertised to.

Now use the state:

- **Same values again.** The plan finds nothing to change, **Routers match the
  state?** confirms the routers carry what the state says, and the run ends at
  **Nothing to change**, without an approval.
- **Move the service.** Run it with `10.255.100.21`. The plan shows the change
  from the stored address (*Plan: +0 ~2 -0*, `10.255.100.20/32 ->
  10.255.100.21/32`). After approval, **Remove the old address** takes the old
  one off both edges (the stored state is how the flow knows it) before the
  push adds the new one. **Terraform States** now holds two versions.
- **Pick it from the catalogue.** With `service_catalog.enabled: true` in
  `spec/basic.yaml` (it needs a platform release and Git inventory plugin 0.5.0
  or later in `platform.env`), the Git inventory also carries a service
  catalogue: **Inventory** lists *Services* and *Service addresses* from
  `netops/inventory`. The form then offers `portal` from a list, and the
  address list shows only that service's addresses: the primary
  `10.255.100.20` and the replacement `10.255.100.21`, so moving the service
  is a pick, not a typed address.
- **A change by hand.** In the demo directory, remove the address from one
  edge, as someone in a hurry would:

  ```sh
  deploy/lab/lab.sh exec dlp1-edge-01 vtysh -c 'configure terminal' \
    -c 'interface lo' -c 'no ip address 10.255.100.21/32'
  ```

  Run the flow again with `10.255.100.21`. The code did not change, so the
  plan is clean, but **Routers match the state?** finds `dlp1-edge-01`
  missing the address, and **Approve the repair** names it. After approval
  the push puts it back.

## 5. Every change in Git

*Every router's configuration, in Git, with a commit for every change.*

1. As **`noc`**, run **Configuration backup** with the defaults: the three
   Delphi routers. An Ansible playbook reads each running configuration over
   SSH and commits it to the lab's Gitea, one file per router.
2. Open <http://localhost:3000/netops/config-backups>: the commit names the run,
   and `routers/dlp1-edge-01.cfg` carries the `portal` address from story 4 (and
   story 1's, if you ran it).
3. Run the backup again: nothing changed, so there is no new commit. Every
   commit in the history is a change to the network.

The schedule **Nightly configuration backup** ships disabled; enable it under
**Schedules** for a backup every night.

## Afterwards

- **Artifacts → Container Images** lists the images the container steps
  pulled (stories 3 to 5): the platform's own registry keeps a copy of each,
  so a story's next run does not ask the image's registry again.
- `task down` stops the demo and keeps everything; `task up` starts it again.
- `task reset` deletes all runs, approvals and settings; the next `task up`
  starts from the generated data again.
- Everything the demo contains comes from [`spec/basic.yaml`](../spec/basic.yaml)
  and the templates in [`stories/`](../stories/). Change the spec, run
  `uv run demo-gen`, then `task reset` and `task up` to see your change.
