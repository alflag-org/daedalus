# Operations

Use Atlas or the generated `infra` shim for production runs:

```bash
atlas run infra check
atlas run infra diff --site kanagawa01 --limit cap_control_node
atlas run infra apply --yes --site kanagawa01 --limit svc_dns_recursive
```

Use `infra sites` and `infra playbooks` before targeting a non-default site or
public playbook entrypoint.

The `infra` wrapper installs missing Ansible collections from
`ansible/collections/requirements.yml` before playbook runs, so normal Atlas
runs do not need a separate `ansible-galaxy collection install` step.

Normal steady-state runs should use the default `site` playbook and narrow the
target with `--limit <inventory-group-or-host>` when needed. Reserve
`--playbook bootstrap` for first converge on a newly added Atlas-managed host.
Use `--playbook cloudflare` deliberately for host-side Cloudflare components;
it is not part of the default `site` converge because connector hosts require
operator-provided tunnel tokens for apply runs.

`apply` is the only mutating action and requires `--yes`. Run `check` or `diff`
first unless there is a clear operational reason not to.

Keep plaintext secrets out of git. Keep shared secret values in the agreed
operator secret store, and pass operator-local vars from files outside this
repository.

The `infra` wrapper automatically loads the first existing site-local operator
vars file from:

```text
~/.config/daedalus/<site>.yml
~/.config/daedalus/<site>.yaml
~/.config/daedalus/<site>.json
```

Set `DAEDALUS_OPERATOR_VARS=/path/to/vars.yml` when an operator run needs a
different file. Explicit `--extra-vars` still works and is applied after the
auto-loaded file.

For the managed Zabbix server, apply runs require these workload database
variables:

```yaml
mysql_zabbix_password: ...
mysql_zabbix_monitor_password: ...
```

The local MySQL root account is managed over the Unix socket and does not need
an operator-provided database password.

Store them in the KANAGAWA01 operator vars file:

```bash
mkdir -p /home/ops/.config/daedalus
umask 077
cat > /home/ops/.config/daedalus/kanagawa01.yml <<'EOF'
mysql_zabbix_password: ...
mysql_zabbix_monitor_password: ...
EOF
```

Then normal targeted runs do not need a repeated `--extra-vars` argument:

```bash
atlas run infra apply --yes --site kanagawa01 --limit kng01-mgmt-zabbix-01
```

The shared MySQL data service at `kng01-mgmt-mysql-01` currently has no
workload databases or users declared, so it does not require an operator secret
by default. When adding a consumer, declare its database/user entries through
`mysql_server_databases` and `mysql_server_users`, and list any required secret
variable names in `mysql_server_required_secret_vars`.

If the initial Zabbix schema import fails partway through a fresh provisioning
run, the next apply stops when it detects the partial database instead of
treating it as complete. For a fresh host where the Zabbix database can be
discarded, add this one-time operator var and rerun the targeted apply:

```yaml
zabbix_server_recreate_partial_schema: true
```
