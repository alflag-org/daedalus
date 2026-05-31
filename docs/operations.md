# Operations

Use Atlas or the generated `infra` shim for production runs:

```bash
atlas run infra check
atlas run infra diff --site kanagawa01 --playbook baseline
atlas run infra apply --yes --site kanagawa01 --playbook baseline
```

Use `infra sites` and `infra playbooks` before targeting a non-default site or
playbook.

`apply` is the only mutating action and requires `--yes`. Run `check` or `diff`
first unless there is a clear operational reason not to.

Keep plaintext secrets out of git. Use `secrets/ansible_vault.env` for local
Vault password material and keep shared secret values in the agreed operator
secret store.
