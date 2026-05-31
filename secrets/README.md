# Secrets

This directory is for machine-local secret material used by Daedalus operator
commands. It is intentionally ignored by git except for this README, `.gitignore`,
and sample files.

## Ansible Vault Password

`tools/vault_pass.sh` reads the Vault password from either:

```text
ANSIBLE_VAULT_PASSWORD
secrets/ansible_vault.env
```

Create the local env file from the tracked sample when needed:

```bash
cp secrets/ansible_vault.env.sample secrets/ansible_vault.env
```

The local file should contain:

```text
ANSIBLE_VAULT_PASSWORD=...
```

Do not commit plaintext secret files. Keep shared secret values in the agreed
operator secret store, and keep only encrypted Ansible Vault files in git.
