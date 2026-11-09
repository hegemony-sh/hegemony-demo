# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Render the story templates into bundle sections, per organization.

A story is a folder `stories/<id>/` with a `story.yaml.j2` template. The
template renders, once per organization the spec assigns the story to, into a
partial bundle: `flows`, `flow_attachments`, `notification_destinations`,
`flow_subscriptions` and `schedules`. A flow attachment names a file of the
story folder with `source:`, and its content is read from there.

The templates use `[[ ... ]]` and `[% ... %]` as delimiters, so the platform's
own `{{ ... }}` and `{% ... %}` templates in a flow pass through untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jinja2
import yaml

from . import catalog as catalogmod
from . import lab as labmod
from .model import Device, Model
from .spec import SpecError

SECTIONS = (
    "flows",
    "flow_attachments",
    "notification_destinations",
    "flow_subscriptions",
    "schedules",
)


@dataclass
class StoryOutput:
    flows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    flow_attachments: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    destinations: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    flow_subscriptions: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    schedules: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


def _environment(folder: Path) -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(folder)),
        variable_start_string="[[",
        variable_end_string="]]",
        block_start_string="[%",
        block_end_string="%]",
        comment_start_string="[#",
        comment_end_string="#]",
        undefined=jinja2.StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,  # noqa: S701 - renders YAML, not HTML
    )


def _context(model: Model, org_slug: str) -> dict[str, Any]:
    org = model.org(org_slug)

    def devices(role: str | None = None, *, live: bool | None = None) -> list[Device]:
        return [
            d
            for d in model.devices_of(org_slug, source="bundle")
            if (role is None or d.role == role) and (live is None or d.live == live)
        ]

    contact = model.contacts.get(org_slug)
    return {
        "model": model,
        "org": org,
        "devices": devices,
        "noc_email": model.email(contact.mailbox if contact else "noc", org_slug),
        "sender": model.email("hegemony", org_slug),
        "email": model.email,
        "lab": model.lab,
        "catalog": model.catalog,
        "catalog_types": {"service": catalogmod.SERVICE_TYPE, "address": catalogmod.ADDRESS_TYPE},
        "git_backup_url": labmod.sandbox_git_url(model.lab, labmod.GIT_BACKUP_REPO),
        "git_backup_web": f"http://localhost:{labmod.GIT_PORT}/{labmod.GIT_ORG}/"
        + labmod.GIT_BACKUP_REPO,
    }


def _add(target: dict[str, list[dict[str, Any]]], org: str, items: list[dict[str, Any]]) -> None:
    bucket = target.setdefault(org, [])
    for item in items:
        same = [i for i in bucket if i.get("name") == item.get("name") and "name" in item]
        if same and same[0] != item:
            raise SpecError(f"{org}: two stories define {item.get('name')!r} differently")
        if not same:
            bucket.append(item)


def render_stories(model: Model, stories_root: Path) -> StoryOutput:
    out = StoryOutput()
    for story in model.stories:
        folder = stories_root / story.id
        template_path = folder / "story.yaml.j2"
        if not template_path.is_file():
            raise SpecError(f"story {story.id}: {template_path} is missing")
        template = _environment(folder).get_template("story.yaml.j2")
        for org_slug in story.orgs:
            text = template.render(**_context(model, org_slug))
            data = yaml.safe_load(text) or {}
            unknown = set(data) - set(SECTIONS)
            if unknown:
                raise SpecError(f"story {story.id}: unknown sections {sorted(unknown)}")
            attachments = []
            for item in data.get("flow_attachments", []):
                source = folder / item.pop("source")
                if folder.resolve() not in source.resolve().parents:
                    raise SpecError(f"story {story.id}: attachment outside the story folder")
                attachments.append({**item, "content": source.read_text(encoding="utf-8")})
            _add(out.flows, org_slug, data.get("flows", []))
            _add(out.flow_attachments, org_slug, attachments)
            _add(out.destinations, org_slug, data.get("notification_destinations", []))
            _add(out.flow_subscriptions, org_slug, data.get("flow_subscriptions", []))
            _add(out.schedules, org_slug, data.get("schedules", []))
    return out
