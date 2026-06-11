# KANAGAWA01 Components

Daedalus models KANAGAWA01 host configuration as inventory-selected
components. Inventory describes which hosts exist, their network zone, platform
class, and enabled component flags. Roles implement host-side state only.

## Playbooks

The steady-state entrypoint is:

```bash
atlas run infra check --site kanagawa01
```

Public compatibility playbook names still exist for focused runs:

```bash
atlas run infra check --site kanagawa01 --playbook baseline
atlas run infra check --site kanagawa01 --playbook dns
atlas run infra check --site kanagawa01 --playbook monitoring
atlas run infra check --site kanagawa01 --playbook containers
atlas run infra check --site kanagawa01 --playbook cloudflare
atlas run infra check --site kanagawa01 --playbook atlas
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
| `docker_host` | `docker_host_enabled` | Prepares Docker hosts only when explicitly enabled. No application containers are deployed. |
| `vector_agent` | `vector_agent_enabled` | Reserved skeleton for future log forwarding. It does not configure external sinks. |

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
require `cloudflared_tunnel_token` from Vault, an untracked vars file, or an
operator-provided extra var.

## External State

Daedalus does not currently manage:

- Cloudflare Access applications
- Cloudflare tunnel routes
- Cloudflare tunnel tokens
- Cloudflare private hostnames
- Cloudflare dashboard state
- Zabbix server provisioning
- application containers
- authoritative DNS zone migration unless `dns_authoritative_zones` explicitly
  provides zone text

Those boundaries are deliberate. They can move to Terraform or a future
Daedalus component after the host-side state is stable.

## Validation

On the control node, use:

```bash
atlas run infra inventory --site kanagawa01
atlas run infra check --site kanagawa01 --playbook baseline --limit kng01-mgmt-recdns-01
atlas run infra check --site kanagawa01 --playbook dns --limit kng01-mgmt-recdns-01
atlas run infra check --site kanagawa01 --playbook cloudflare --limit kng01-mgmt-connector-01
atlas run infra check --site kanagawa01 --playbook cloudflare --limit kng01-mgmt-bastion-01
atlas run infra check --site kanagawa01 --playbook monitoring --limit kng01-mgmt-recdns-01
atlas run infra check --site kanagawa01 --playbook atlas --limit kng01-mgmt-control-01
atlas run infra ping --site kanagawa01 --limit kng01-dmz-web-01
atlas run infra check --site kanagawa01 --limit kng01-dmz-web-01
atlas run infra check --site kanagawa01 --playbook cloudflare --limit kng01-dmz-web-01
```

After applying the site playbook to `kng01-dmz-web-01`, the origin health check
is available on the host at:

```bash
curl http://127.0.0.1:8080/healthz
```

Local development machines may lack Atlas runtime, Vault password material, or
`~/.ssh/infra`. In that case, use repository-local syntax checks as a static
guard and run the commands above from `kng01-mgmt-control-01`.
