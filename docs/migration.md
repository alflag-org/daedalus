# Migration Notes

Daedalus previously kept Ansible files at the repository root. They now live
under `ansible/`.

Path changes:

```text
ansible.cfg        -> ansible/ansible.cfg
inventories/      -> ansible/inventories/
playbooks/        -> ansible/playbooks/
roles/            -> ansible/roles/
group_vars/       -> ansible/inventories/default/group_vars/ or removed when legacy-only
```

Current playbook structure:

```text
ansible/playbooks/site.yml
ansible/playbooks/bootstrap.yml
ansible/playbooks/cloudflare.yml
ansible/playbooks/components/
```

`site.yml` is the steady-state converge entrypoint. `bootstrap.yml` is the
first-converge entrypoint for a new Atlas-managed host. Deprecated playbook
aliases such as `atlas`, `baseline`, `dns`, `monitoring`, and `containers` have
been removed; focused checks should use `site` with `--limit`, or a real
top-level playbook such as `cloudflare`.

The Python package was renamed from `alflag_infra` to `daedalus`. The operator
command remains `infra`.

The legacy `onp/` playbooks and the self-installing `roles/middleware/daedalus`
role were removed from the normal backend because Atlas is responsible for
installing Daedalus.

The former `roles/common/*` platform helpers were folded into explicit
`roles/foundation/*` roles. Host metrics now use the dedicated `node_exporter`
role from the foundation playbook.

The former `roles/middleware/*` service internals moved under
`roles/components/*`. `roles/services/*` remains the public service intent
surface and includes those component roles internally.

Monitoring uses the Prometheus stack documented in
[monitoring.md](monitoring.md). Daedalus no longer installs Zabbix Agent or
converges Zabbix server/frontend roles.

The legacy top-level `group_vars/` tree belonged to the removed root inventory
and was removed with it. Active inventory variables now live under
`ansible/inventories/default/group_vars/`.

Host responsibility is now modeled primarily through inventory groups:

- `platform_*`
- `provider_*`
- `cap_*`
- `svc_*`
