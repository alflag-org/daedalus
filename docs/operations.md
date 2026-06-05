# Operations

Use Atlas or the generated `infra` shim for production runs:

```bash
atlas run infra check
atlas run infra diff --site kanagawa01 --limit cap_control_node
atlas run infra apply --yes --site kanagawa01 --limit svc_dns_recursive
```

Use `infra sites` and `infra playbooks` before targeting a non-default site or
public playbook entrypoint.

Normal steady-state runs should use the default `site` playbook and narrow the
target with `--limit <inventory-group-or-host>` when needed. Reserve
`--playbook bootstrap` for first converge on a newly added Atlas-managed host.
Use `--playbook cloudflare` deliberately for host-side Cloudflare components;
it is not part of the default `site` converge because connector hosts require
operator-provided tunnel tokens for apply runs.

`apply` is the only mutating action and requires `--yes`. Run `check` or `diff`
first unless there is a clear operational reason not to.

Keep plaintext secrets out of git. Use `secrets/ansible_vault.env` for local
Vault password material and keep shared secret values in the agreed operator
secret store.
