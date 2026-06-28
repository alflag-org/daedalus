# Operations

Use Atlas or the generated `infra` shim for production runs:

```bash
atlas run infra check
atlas run infra diff --site topmost01 --limit cap_control_node
atlas run infra apply --yes --site topmost01 --limit svc_dns_recursive
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

The monitoring stack does not need operator-provided secrets for the initial
Prometheus, Grafana, Alertmanager, and blackbox exporter converge. Target it as
a normal service group:

```bash
atlas run infra check --site topmost01 --limit svc_monitoring
atlas run infra apply --yes --site topmost01 --limit svc_monitoring
```

Prometheus reads file-based service discovery targets prepared under
`/var/lib/prometheus/file_sd`. Daedalus creates the directory and configures
Prometheus to read it. Hermes owns the generated target files.

The foundation converge includes a temporary cleanup role for hosts that
previously received Zabbix packages from Daedalus. It purges those packages and
removes their old local state before `node_exporter` becomes the active host
metrics agent.

The shared MySQL service is not part of the monitoring migration. It remains a
generic data service with no workload databases or users declared by default.
Do not remove it as part of Zabbix cleanup unless that is made as a separate
explicit infrastructure decision.

Grafana and Prometheus should stay behind MGMT-only access or Cloudflare Access.
Do not expose either UI directly to the Internet.
