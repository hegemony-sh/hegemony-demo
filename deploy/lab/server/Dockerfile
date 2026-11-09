# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# A simulated Linux server: Alpine with an SSH server, Python and sudo, so
# Ansible manages it like any other host. Built locally by the lab's Compose
# project; it holds no password (the entrypoint sets it at start).
FROM public.ecr.aws/docker/library/alpine:3.22

RUN apk add --no-cache openssh-server python3 sudo iproute2 \
    && sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config \
    && sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config \
    && adduser -D -s /bin/sh netops \
    && echo 'netops ALL=(ALL) ALL' > /etc/sudoers.d/netops \
    && chmod 0440 /etc/sudoers.d/netops

COPY --chmod=0755 entrypoint.sh /usr/local/bin/server-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/server-entrypoint.sh"]
