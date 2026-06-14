# KANAGAWA01 Components

Daedalus models KANAGAWA01 host configuration as inventory-selected
components. Inventory describes which hosts exist, their network zone, platform
class, and enabled component flags. Roles implement host-side state only.

## Playbooks

The steady-state entrypoint is:

```bash
atlas run infra check --site kanagawa01
```

Focused runs use the normal `site` playbook plus `--limit`. `cloudflare` is the
only explicit host-side component playbook outside normal `site` because apply
runs require operator-provided tunnel tokens:

```bash
atlas run infra check --site kanagawa01 --limit svc_dns_recursive
atlas run infra check --site kanagawa01 --limit cap_control_node
atlas run infra check --site kanagawa01 --playbook cloudflare
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
| `dns_recursor` | `dns_recursor_enabled` | Installs and configures Unbound for recursive DNS hosts. |
| `dns_authoritative` | `dns_authoritative_enabled` | Installs and minimally configures NSD. It starts the service only when zones are explicitly provided. |
| `services/web` | `services_web_origin_enabled` | Installs nginx as a lightweight localhost-bound Web origin, renders a default page, and validates a health endpoint. |
| `zabbix_agent` | `zabbix_agent_enabled` | Installs and configures `zabbix-agent2` on managed hosts. |
| `services/mysql` | `mysql_server_enabled` | Converges the shared MySQL data service using the reusable MySQL server internals. |
| `services/zabbix` | `zabbix_server_installation_managed` | Converges the managed Zabbix host using local MySQL, Caddy, PHP-FPM, and Zabbix server/frontend internals. |

All risky roles default to disabled. Host vars opt a host into the components it
should run.

## Host Responsibility

Current KANAGAWA01 component flags are:

| Host | Connection policy | Components |
| --- | --- | --- |
| `kng01-mgmt-control-01` | local connection, `ops + become` | Atlas control host validation, SSH server, Zabbix agent |
| `kng01-mgmt-recdns-01` | LXC root, no become | Recursive DNS, Zabbix agent |
| `kng01-mgmt-recdns-02` | LXC root, no become | Recursive DNS, Zabbix agent |
| `kng01-mgmt-authdns-01` | LXC root, no become | Authoritative DNS foundation, Zabbix agent |
| `kng01-mgmt-authdns-02` | LXC root, no become | Authoritative DNS foundation, Zabbix agent |
| `kng01-mgmt-connector-01` | LXC root, no become | cloudflared, Zabbix agent |
| `kng01-mgmt-connector-02` | LXC root, no become | cloudflared, Zabbix agent |
| `kng01-mgmt-bastion-01` | LXC root, no become | SSH server, Cloudflare SSH target, Zabbix agent |
| `kng01-mgmt-workbench-01` | LXC root, no become | SSH server, Cloudflare SSH target, Zabbix agent |
| `kng01-mgmt-zabbix-01` | VM `ops + become` | Caddy-backed Zabbix server/frontend/local DB, Zabbix agent |
| `kng01-mgmt-mysql-shared-01` | VM `ops + become` | Shared MySQL data service, Zabbix agent |
| `kng01-dmz-web-01` | VM `ops + become` | SSH server, cloudflared host-side readiness, Cloudflare SSH target, localhost nginx Web origin, Zabbix agent |

The LXC connection policy reflects the current inventory state. VM hosts should
use the normal `ops + become` model unless host-specific reality says
otherwise.

`kng01-dmz-web-01` is the first DMZ Web origin host. It is registered in VLAN
130 at `10.10.30.21/24` with gateway `10.10.30.1`. Its nginx origin binds to
`127.0.0.1:8080` by default, so WAN-direct inbound `80`/`443` is not part of
this host contract. A later Cloudflare Tunnel or Access change should route to
that local service URL or deliberately override the bind address.
The host is opted into the existing `cloudflared` role, but apply runs still
require `cloudflared_tunnel_token` from the operator secret store, an untracked
vars file, or an operator-provided extra var.

`kng01-mgmt-zabbix-01` is reserved for the primary Zabbix service in VLAN 110
because monitoring and problem triage are management-plane responsibilities.
The inventory classifies it as an Ubuntu 26.04 Proxmox VM in `kng01_mgmt`,
`platform_vm`, and `svc_zabbix`. Daedalus manages the VM foundation, SSH policy,
systemd-resolved policy, `zabbix-agent2`, local MySQL, PHP-FPM, Caddy, and the
Zabbix server/frontend packages for the host. Zabbix consumes
`middleware/mysql-server` as a workload-defined local database: `svc_zabbix`
declares the Zabbix database, application user, and monitor user, while the
Zabbix role owns only the Zabbix schema import and application configuration.
The managed frontend listens on HTTP port 80 through Caddy and serves
`zabbix.alflag.internal` via the host's normal management-plane address. Apply
runs require the database secret vars `mysql_zabbix_password` and
`mysql_zabbix_monitor_password` from the operator secret store, the site-local
operator vars file loaded by `infra`, or operator-provided extra vars. The local
MySQL root account is managed over the Unix socket and does not need an
operator-provided database password. The VM is expected to exist before
Daedalus runs; Daedalus manages the guest configuration after it is reachable at
`10.10.10.250`.

`kng01-mgmt-mysql-shared-01` is the shared MySQL data service host in VLAN 110. The
inventory classifies it as an Ubuntu 26.04 Proxmox VM in `kng01_mgmt`,
`platform_vm`, and `svc_mysql`. Daedalus installs MySQL through
`middleware/mysql-server`, binds it to `10.10.10.251`, and keeps database/user
provisioning driven by `mysql_server_databases` and `mysql_server_users`. Those
lists are intentionally empty at introduction time; add workload-specific
databases, users, and required secret vars to `svc_mysql` or narrower inventory
vars when a consumer is ready. The VM is expected to exist before Daedalus runs;
Daedalus manages the guest configuration after it is reachable at
`10.10.10.251`.

Prometheus, Grafana, Alertmanager, Zabbix HA, and historical Zabbix database
migration are intentionally out of scope for this host definition.

## Network Allocation

| Host | Zone | VLAN | Address | Gateway |
| --- | --- | ---: | --- | --- |
| `kng01-mgmt-connector-01` | mgmt | 110 | `10.10.10.41/24` | `10.10.10.1` |
| `kng01-mgmt-connector-02` | mgmt | 110 | `10.10.10.42/24` | `10.10.10.1` |
| `kng01-mgmt-bastion-01` | mgmt | 110 | `10.10.10.60/24` | `10.10.10.1` |
| `kng01-mgmt-workbench-01` | mgmt | 110 | `10.10.10.61/24` | `10.10.10.1` |
| `kng01-mgmt-control-01` | mgmt | 110 | `10.10.10.62/24` | `10.10.10.1` |
| `kng01-mgmt-recdns-01` | mgmt | 110 | `10.10.10.240/24` | `10.10.10.1` |
| `kng01-mgmt-recdns-02` | mgmt | 110 | `10.10.10.241/24` | `10.10.10.1` |
| `kng01-mgmt-authdns-01` | mgmt | 110 | `10.10.10.242/24` | `10.10.10.1` |
| `kng01-mgmt-authdns-02` | mgmt | 110 | `10.10.10.243/24` | `10.10.10.1` |
| `kng01-mgmt-zabbix-01` | mgmt | 110 | `10.10.10.250/24` | `10.10.10.1` |
| `kng01-mgmt-mysql-shared-01` | mgmt | 110 | `10.10.10.251/24` | `10.10.10.1` |
| `kng01-dmz-web-01` | dmz | 130 | `10.10.30.21/24` | `10.10.30.1` |

KANAGAWA01 recursive DNS resolvers are `10.10.10.240` and `10.10.10.241`.
`kng01-mgmt-zabbix-01` uses those resolver addresses in inventory metadata.

## Required Internal DNS Records

Daedalus does not currently keep `alflag.internal` zone records as managed
inventory data. Until that source of truth moves into Daedalus, create or verify
these records in the authoritative internal DNS system:

| Name | Type | Value |
| --- | --- | --- |
| `kng01-mgmt-zabbix-01.srv.alflag.internal` | A | `10.10.10.250` |
| `zabbix.alflag.internal` | CNAME | `kng01-mgmt-zabbix-01.srv.alflag.internal` |
| `kng01-mgmt-mysql-shared-01.srv.alflag.internal` | A | `10.10.10.251` |
| `mysql.alflag.internal` | CNAME | `kng01-mgmt-mysql-shared-01.srv.alflag.internal` |

## External State

Daedalus does not currently manage:

- Cloudflare Access applications
- Cloudflare tunnel routes
- Cloudflare tunnel tokens
- Cloudflare private hostnames
- Cloudflare dashboard state
- Zabbix application objects, templates, users, or dashboard content
- plaintext Zabbix database secret storage
- Prometheus, Grafana, or Alertmanager deployment
- application containers
- authoritative DNS zone migration unless `dns_authoritative_zones` explicitly
  provides zone text

Those boundaries are deliberate. They can move to Terraform or a future
Daedalus component after the host-side state is stable.

## Validation

On the control node, use:

```bash
atlas run infra inventory --site kanagawa01
atlas run infra check --site kanagawa01 --limit kng01-mgmt-recdns-01
atlas run infra check --site kanagawa01 --playbook cloudflare --limit kng01-mgmt-connector-01
atlas run infra check --site kanagawa01 --playbook cloudflare --limit kng01-mgmt-bastion-01
atlas run infra check --site kanagawa01 --limit kng01-mgmt-control-01
atlas run infra ping --site kanagawa01 --limit kng01-mgmt-zabbix-01
atlas run infra check --site kanagawa01 --playbook bootstrap --limit kng01-mgmt-zabbix-01
atlas run infra check --site kanagawa01 --limit kng01-mgmt-zabbix-01
curl http://zabbix.alflag.internal/
atlas run infra ping --site kanagawa01 --limit kng01-mgmt-mysql-shared-01
atlas run infra check --site kanagawa01 --playbook bootstrap --limit kng01-mgmt-mysql-shared-01
atlas run infra check --site kanagawa01 --limit kng01-mgmt-mysql-shared-01
atlas run infra ping --site kanagawa01 --limit kng01-dmz-web-01
atlas run infra check --site kanagawa01 --limit kng01-dmz-web-01
atlas run infra check --site kanagawa01 --playbook cloudflare --limit kng01-dmz-web-01
```

After applying the site playbook to `kng01-dmz-web-01`, the origin health check
is available on the host at:

```bash
curl http://127.0.0.1:8080/healthz
```

Local development machines may lack Atlas runtime, operator secret material, or
`~/.ssh/infra`. In that case, use repository-local syntax checks as a static
guard and run the commands above from `kng01-mgmt-control-01`.
