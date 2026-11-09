// SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
// SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
//
// SPDX-License-Identifier: AGPL-3.0-or-later

// Conventional Commits — commitlint configuration
// Docs: https://commitlint.js.org/reference/configuration.html
//
// JavaScript rather than YAML because `ignores` only accepts predicate
// functions, which YAML cannot express. .mjs specifically:
// wagoid/commitlint-github-action rejects a .js configFile.
//
// The same rules as the platform and plugin repositories. They also exempt
// semantic-release's commit; this repository tags its releases by hand
// (CONTRIBUTING.md), so it has no such commit to exempt.

// Dependabot writes its own commit message and cannot be told to wrap it. Its
// first body line links the package by name, so a long package name runs past
// body-max-line-length. It sends the security updates for uv.lock here.
const DEPENDABOT_SIGNOFF = /^Signed-off-by: dependabot\[bot\] <support@github\.com>$/m;

// Scopes are free-form, so nobody has to look up a list: one or more
// comma-separated names (generator, lab, stories,docs), each lower-case
// letters, digits and single dashes, at most SCOPE_MAX_LENGTH characters. A
// fixed list keeps rejecting new areas and sending authors to reword and
// force-push; CONTRIBUTING.md lists the common ones as guidance.
const SCOPE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const SCOPE_MAX_LENGTH = 20;

function scopeFormat({ scope }) {
  if (!scope) {
    return [true];
  }
  const bad = scope
    .split(",")
    .filter((name) => !SCOPE.test(name) || name.length > SCOPE_MAX_LENGTH);
  return [
    bad.length === 0,
    `scope names must be lower-case letters, digits and single dashes, at most ` +
      `${SCOPE_MAX_LENGTH} characters, comma-separated without spaces ` +
      `(e.g. generator, lab, stories,docs); not: ${bad.map((name) => JSON.stringify(name)).join(", ")}`,
  ];
}

export default {
  extends: ["@commitlint/config-conventional"],

  plugins: [{ rules: { "scope-format": scopeFormat } }],

  ignores: [(message) => DEPENDABOT_SIGNOFF.test(message)],

  rules: {
    // Any scope, in one shape: see SCOPE above.
    "scope-format": [2, "always"],
    // Subjects legitimately begin with identifiers that carry their own
    // capitalization (OpenTofu, FRR, NOC, s4); the inherited subject-case
    // rule false-flags them, as in the platform repository.
    "subject-case": [0],
  },
};
