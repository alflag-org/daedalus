# Components

Daedalus models host configuration as inventory-selected components. Inventory
describes which hosts exist, their network zone, platform class, and enabled
component flags. Roles implement host-side state only.

## Playbooks

The steady-state entrypoint is:

```bash
atlas run infra check --site default
```

Focused runs use the normal `site` playbook plus `--limit`. `cloudflare` is the
only explicit host-side component playbook outside normal `site` because apply
runs require operator-provided tunnel tokens:

```bash
atlas run infra check --site default --limit svc_dns_recursive
atlas run infra check --site default --limit cap_control_node
atlas run infra check --site default --playbook cloudflare
```

`cloudflare` is intentionally explicit and is not imported into `site.yml`.
Cloudflare tunnel tokens are required for apply runs on connector hosts, so
operators should target that playbook deliberately.

## Implemented Roles

| Role | Flag | Purpose |
| --- | --- | --- |
| `ssh_server` | `ssh_server_enabled` | Installs OpenSSH server, writes a conservative drop-in, validates `sshd -t`, and restarts SSH only after config changes. TCP forwarding accepts `no`, `local`, or `yes` and defaults to `no`. |
| `cloudflared` | `cloudflared_enabled` | Installs cloudflared, writes a token environment file from operator-provided secret vars, installs the systemd service, and validates local service state. |
| `cloudflare_ssh_target` | `cloudflare_ssh_enabled` | Ensures local SSH is available for Cloudflare Access SSH or Tunnel routing. It performs no Cloudflare API calls. |
| `systemd_resolved` | `systemd_resolved_enabled` | Configures systemd-resolved. `/etc/resolv.conf` is managed only when `systemd_resolved_manage_resolv_conf` is true. |
| `dns_recursor` | `dns_recursor_enabled` | Installs and configures Unbound for recursive DNS hosts, including internal stub-zone or forward-zone metadata. |
| `dns_authoritative` | `dns_authoritative_enabled` | Installs and configures NSD from managed zone metadata and structured zone contents. |
| `services/web` | `services_web_origin_enabled` | Installs nginx as a lightweight localhost-bound Web origin, renders a default page, and validates a health endpoint. |
| `services/mysql` | `mysql_server_enabled` | Converges the generic shared MySQL data service using private `components/mysql_server` internals. It is independent from monitoring. |
| `retired_monitoring_cleanup` | `retired_monitoring_cleanup_enabled` | Temporary migration role that removes old Zabbix services, packages, repositories, and local state from hosts. |
| `node_exporter` | `node_exporter_enabled` | Installs `prometheus-node-exporter` on monitored hosts and renders its system defaults. |
| `services/monitoring` | `monitoring_stack_enabled` | Converges the monitoring service host using private Prometheus, Alertmanager, Grafana, and blackbox exporter component roles. |

All risky roles default to disabled. Host vars opt a host into the components it
should run.

## Host Responsibility

Inventory is the source of truth for current host membership, platform class,
connection policy, network metadata, and enabled component flags. Do not copy
those values into docs. Use the inventory graph and host/group vars when current
state is needed:

```bash
infra inventory --site default
```

The docs describe role boundaries and operating contracts. Host additions,
service moves, address changes, alias changes, and lifecycle decisions should be
expressed in `ansible/inventories/default/hosts.yml`, `group_vars/`, and
`host_vars/`, with tests guarding the expected state.

Platform intent should stay explicit:

- VM hosts use the normal `ops + become` model unless inventory says otherwise.
- LXC hosts may still use a root bootstrap connection while they converge toward
  the same steady-state operator model.
- `svc_*` groups express service intent; `components/*` roles are implementation
  details and are not selected directly from inventory.

Service-specific host metadata, DNS aliases, bind addresses, and validation
targets belong in inventory vars. Documentation should link to that source of
truth rather than restating it.

## DNS Boundary

Daedalus manages DNS server packages, service state, listen addresses, host
configuration, and managed authoritative zone contents. Recursive DNS hosts run
Unbound and stub internal zones to the authoritative DNS hosts. Authoritative
DNS hosts run NSD from inventory-backed zone registration and generated zone
files. See [docs/dns.md](dns.md) for the operational boundary and validation
commands.

## Required Internal DNS Records

Daedalus keeps managed authoritative DNS record contents in inventory vars. DNS
names, aliases, and address metadata that are needed by services belong in
inventory vars.

Do not duplicate DNS record values in docs. Use inventory metadata and generated
authoritative zone files when records need to be created or verified.

## External State

Daedalus does not currently manage:

- Cloudflare Access applications
- Cloudflare tunnel routes
- Cloudflare tunnel tokens
- Cloudflare private hostnames
- Cloudflare dashboard state
- Prometheus file service-discovery target generation
- Alertmanager notification receivers
- Grafana dashboard curation beyond the initial Daedalus provider
- application containers
- DNSSEC signing
- external DNS zone writes

Those boundaries are deliberate. They can move to Terraform or a future
Daedalus component after the host-side state is stable.

## Validation

On the control node, use:

```bash
atlas run infra inventory --site default
atlas run infra check --site default --limit dns-recursive01
atlas run infra check --site default --playbook cloudflare --limit connector01
atlas run infra check --site default --playbook cloudflare --limit bastion01
atlas run infra check --site default --limit control01
atlas run infra ping --site default --limit monitor01
atlas run infra check --site default --playbook bootstrap --limit monitor01
atlas run infra check --site default --limit svc_monitoring
atlas run infra check --site default --limit svc_mysql
atlas run infra ping --site default --limit web01
atlas run infra check --site default --limit web01
atlas run infra check --site default --playbook cloudflare --limit web01
```

Local development machines may lack Atlas runtime, operator secret material, or
`~/.ssh/infra`. In that case, use repository-local syntax checks as a static
guard and run the commands above from `control01`.
