# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# The lab console: a page with the lab diagram (nginx) and a terminal per
# device (ttyd), logged in by connect.sh. Built locally by the lab's Compose
# project; the logins, host keys and diagram data are mounted at start. Runs
# as an unprivileged user. The base is pinned by digest (the
# multi-architecture index); Renovate keeps it current.
FROM public.ecr.aws/docker/library/alpine:3.22@sha256:49340b346798875b5592e5d420241f2f9cfba5f47e62ebb1446a1b34734e898f

RUN apk add --no-cache ttyd nginx openssh-client-default sshpass \
    && adduser -D -s /sbin/nologin console

COPY nginx.conf /etc/console/nginx.conf
COPY www/ /srv/console/
COPY --chmod=0755 entrypoint.sh /usr/local/bin/console-entrypoint
COPY --chmod=0755 connect.sh /usr/local/bin/console-connect
COPY --chmod=0755 health.sh /usr/local/bin/console-health

USER console
EXPOSE 8182
ENTRYPOINT ["/usr/local/bin/console-entrypoint"]
