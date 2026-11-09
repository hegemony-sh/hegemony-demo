# SPDX-FileCopyrightText: 2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Trávník <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# The declared state of one routed service: which edge routers carry its
# address, and how. One terraform_data resource per router, so a plan says
# exactly which routers change. Hegemony keeps the state (managed state,
# versioned and locked), so every plan compares against what the last apply
# left: a new service is added, a new address shows as a change from the old
# one (the flow then removes the old address), and the same values again
# change nothing. Only built-in resources: there is no provider to download
# (FRR has no OpenTofu provider), so the flow writes the apply's outputs to
# the routers, with their logins from Hegemony.
#
# The flow also hands in what each router's loopback carries right now
# (`observed`). OpenTofu uses it as a safety check: it refuses to take an
# address a router already uses for something it does not manage.

variable "service_name" {
  type        = string
  description = "Short service identifier, written into the loopback's description."

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,30}$", var.service_name))
    error_message = "service_name is a short lowercase identifier."
  }
}

variable "service_address" {
  type        = string
  description = "Host address the service answers on, announced as a /32."

  validation {
    condition     = can(regex("^10\\.255\\.100\\.[0-9]{1,3}$", var.service_address))
    error_message = "service_address is a host address in 10.255.100.0/24."
  }
}

variable "routers" {
  type        = list(string)
  description = "Edge routers that carry the service address."
}

variable "observed" {
  # The collect step's output.devices: per router, whether the collection
  # worked and each command's text.
  type        = any
  description = "What each router reported, from the flow's collect step."
}

locals {
  address     = "${var.service_address}/32"
  description = "svc ${var.service_name} managed-by-opentofu"
  marker      = "managed-by-opentofu"
  command     = "show interface lo json"

  # Per router: the loopback as FRR reports it (empty when it did not answer).
  loopback = {
    for router in var.routers : router => try(
      jsondecode(var.observed[router].commands[local.command]).lo, {}
    )
  }
}

resource "terraform_data" "service" {
  for_each = toset(var.routers)

  input = {
    address     = local.address
    description = local.description
  }

  lifecycle {
    precondition {
      condition     = try(var.observed[each.key].success, false)
      error_message = "${each.key} did not report its loopback, so the plan cannot tell whether the address is free."
    }

    # The address is free, or already ours: a loopback that carries it under
    # a description without the marker belongs to something else.
    precondition {
      condition = (
        !contains([for a in try(local.loopback[each.key].ipAddresses, []) : a.address], local.address)
        || strcontains(try(local.loopback[each.key].description, ""), local.marker)
      )
      error_message = "${each.key} already uses ${local.address} for something OpenTofu does not manage."
    }
  }
}

# What the flow's push step writes to the routers: the plan decides it, not
# the flow's inputs. The plan step reports these as the state held them
# before its changes, which is how the flow finds an address to remove.
output "address" {
  description = "The service address with its prefix length, as the routers carry it."
  value       = local.address
}

output "description" {
  description = "The loopback description that marks the address as managed here."
  value       = local.description
}

output "routers" {
  description = "The routers that carry the service."
  value       = sort(var.routers)
}
