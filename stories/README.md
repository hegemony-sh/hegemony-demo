<!--
SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>

SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Stories

Each folder is one story of the demo: a `story.yaml.j2` template that renders
into the bundle sections of the organizations `spec/basic.yaml` assigns it to
(flows, attachments, notification destinations, subscriptions, schedules),
plus any file a flow attaches.

| Story | Organizations | Flow | Shows |
| --- | --- | --- | --- |
| [s1-approved-change](s1-approved-change/) | operator | Announce service prefix | approval with separation of duties, evidence before and after, comparison, mail, audit log |
| [s2-durable-window](s2-durable-window/) | operator | Maintenance window | a long run that survives a worker restart, run limits, a deadline on an approval, a schedule |
| [s3-shared-standards](s3-shared-standards/) | shared (run by Athens and Sparta) | Standards check | shared standards with a tenant override, tenant isolation, a read-only auditor |
| [s4-service-as-code](s4-service-as-code/) | operator | Service as code | OpenTofu with state in Hegemony, the plan's summary in the approval, a proof upstream, a convergence check |
| [s5-config-backup](s5-config-backup/) | operator | Configuration backup | an Ansible playbook committing every router's configuration to Git, only on change; a schedule |

Templates use `[[ ... ]]` and `[% ... %]`, so the platform's own `{{ ... }}`
templates inside a flow pass through as they are. In a template:

- `org` is the organization being rendered (`org.slug`, `org.name`).
- `devices(role, live=...)` lists that organization's devices.
- `noc_email`, `sender` and `email(mailbox, org)` give `.example` addresses.

Flow names, destination names and file names stay theme-free. The walkthrough
in [docs/walkthrough.md](../docs/walkthrough.md) tells each story.
