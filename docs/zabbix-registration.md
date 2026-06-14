# Zabbix Registration

Daedalus inventory is the source of truth for KANAGAWA01 Zabbix host
registration. Avoid manual host creation in the Zabbix UI for Daedalus-managed
Linux VM and LXC hosts; UI edits will be overwritten for managed host groups,
agent interfaces, linked templates, and tags.

The registration playbook is controller-local and talks to the Zabbix JSON-RPC
API:

```bash
atlas run infra check --site kanagawa01 --playbook services/zabbix-registration
atlas run infra apply --yes --site kanagawa01 --playbook services/zabbix-registration
```

Direct Ansible execution is also possible:

```bash
cd ansible
ANSIBLE_CONFIG=ansible.cfg ansible-playbook \
  -i inventories/kanagawa01/hosts.yml \
  playbooks/services/zabbix-registration.yml \
  --check
```

## Managed Scope

The first implementation registers Linux VM/LXC hosts that are managed by
Daedalus and have `zabbix_agent_enabled: true` unless a host explicitly sets
`zabbix_managed: false`. A host can also opt in with `zabbix_managed: true`.

The initial KANAGAWA01 scope covers:

- `kng01-mgmt-zabbix-01`
- recursive DNS hosts
- authoritative DNS hosts
- control, connector, bastion, workbench, and web hosts with Zabbix agents

Network devices and SNMP-only hosts stay out of scope until their inventory
metadata is modeled in Daedalus.

Host deletion is intentionally not automatic. The playbook does not call
`host.delete`, and unmanaged Zabbix hosts are ignored by default.

## Variables

`zabbix_api_url` is a non-secret site variable. For KANAGAWA01 it defaults to:

```yaml
zabbix_api_url: http://zabbix.alflag.internal/api_jsonrpc.php
```

Store `zabbix_api_token` outside the repository, for example in the operator
vars file loaded by `infra`:

```yaml
zabbix_api_token: "..."
```

Useful host-level overrides:

```yaml
zabbix_managed: true
zabbix_host_groups:
  - KANAGAWA01
  - KANAGAWA01/MGMT
  - KANAGAWA01/Monitoring
zabbix_templates:
  - Linux by Zabbix agent
  - Zabbix server health
zabbix_tags:
  - tag: site
    value: kng01
  - tag: zone
    value: mgmt
  - tag: role
    value: zabbix
zabbix_agent_interface:
  useip: true
  ip: 10.10.10.250
  dns: kng01-mgmt-zabbix-01.srv.alflag.internal
  port: "10050"
```

When those overrides are absent, the role derives defaults from
`inventory_hostname`, `ansible_host`, `site`, `zone`, `role`,
`network_primary_fqdn`, `network_service_aliases`, and inventory group
membership.

For `kng01-mgmt-zabbix-01`, the derived state places the host in
`KANAGAWA01`, `KANAGAWA01/MGMT`, and `KANAGAWA01/Monitoring`, uses the agent
interface `10.10.10.250:10050`, links `Linux by Zabbix agent` and
`Zabbix server health`, and tags the host with `site`, `zone`, and `role`.

## API Token

Use a dedicated Zabbix service account or API token. The token must be allowed
to call these API methods:

- `hostgroup.get`
- `hostgroup.create`
- `template.get`
- `host.get`
- `host.create`
- `host.update`

In Zabbix role terms, this generally means an Admin or Super admin token, or a
custom user role with those API methods allowed and read-write access to the
target host groups/templates.

## Check Mode

Check mode reads the Zabbix API and reports planned `create_host_group`,
`create_host`, and `update_host` actions, but it does not mutate Zabbix. Apply
mode performs the same reconciliation and is idempotent: existing hosts are
matched by their Zabbix technical host name and updated instead of duplicated.
