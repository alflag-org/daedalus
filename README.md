# Daedalus

Daedalus is an Atlas script release for operator-triggered Alflag host
configuration management. It is an Ansible-backed configuration runner, not a
daemon and not a general-purpose orchestration service.

```text
Daedalus = Atlas-operated infrastructure configuration runner
```

It gives operators a stable `infra` command for inventory inspection, reachability
checks, dry-run checks, diffs, and explicit applies. Atlas owns the script runtime,
command shims, and run logs; Daedalus owns the Ansible inventories, playbooks,
roles, and the small command wrapper that invokes them.

## Atlas Release Layout

Daedalus follows the Atlas script release shape:

```text
VERSION
commands/infra.py
modules/alflag_infra/
requirements.txt
```

Atlas adds the release `modules/` directory to `PYTHONPATH` before running the
command. `commands/infra.py` maps to the operator command name `infra`.

The Ansible assets used by that command live in the repository as reviewable
configuration:

```text
ansible.cfg
inventories/
playbooks/
roles/
group_vars/
vault_pass.sh
```

`infra` currently defaults to `site=kanagawa01` and `playbook=site`.

## Installation

Install Daedalus as a named Atlas script release, then install the scripts runtime
and regenerate shims when needed:

```bash
atlas scripts install git+https://github.com/alflag-org/daedalus.git#master --name daedalus
atlas runtime install
atlas scripts shims
```

For a local checkout:

```bash
atlas scripts install . --name daedalus
atlas runtime install
atlas scripts shims
```

Operators should run Daedalus through Atlas:

```bash
atlas run infra inventory
atlas run infra ping
atlas run infra check
```

Or add the Atlas shims directory to `PATH` and use the generated shim:

```bash
export PATH="/opt/atlas/shims:$PATH"
infra check
```

Production execution should go through `atlas run` or the shim so Atlas can
provide the release runtime, host context, and JSONL run log. Direct local Python
entrypoints are for development only.

## CLI

Basic shape:

```bash
infra <action> [options]
atlas run infra <action> [options]
```

Inventory and reachability:

```bash
infra inventory
infra ping
infra ping --site kanagawa01 --limit kng01-recursive-dns-01
```

Dry-run validation:

```bash
infra check
infra check --site kanagawa01 --playbook baseline
```

Diff preview:

```bash
infra diff
infra diff --site kanagawa01 --playbook baseline --limit kng01-recursive-dns-01
```

Apply is the mutating action. Run `check` or `diff` first unless there is a clear
operational reason not to.

```bash
infra apply
infra apply --site kanagawa01 --playbook baseline --limit kng01-recursive-dns-01
```

Before invoking Ansible, `infra` prints the exact command it will run. Unknown
sites and playbooks fail before Ansible starts.

## Configuration

Daedalus uses the repository-local `ansible.cfg`. Notable defaults include:

```text
private_key_file=~/.ssh/infra
remote_user=ops
vault_password_file=vault_pass.sh
host_key_checking=False
pipelining=True
ssh_args=-o ForwardAgent=yes
```

`vault_pass.sh` reads the Ansible Vault password from `ANSIBLE_VAULT_PASSWORD` or
from a local, untracked `secrets/ansible_vault.env` file.

Create the local secret file from the sample when needed:

```bash
cp secrets/ansible_vault.env.sample secrets/ansible_vault.env
```

Then set the value in `secrets/ansible_vault.env`:

```text
ANSIBLE_VAULT_PASSWORD=...
```

Do not commit plaintext secrets. Vault-encrypted variable files under
`group_vars/**/vault` are tracked because their contents are encrypted.

## Local Development

Install the Python package in editable mode when working without Atlas:

```bash
python -m pip install -e .
infra inventory
infra ping
infra check
```

The local entrypoint uses the same `modules/alflag_infra` implementation as the
Atlas command. Keep examples and operational docs centered on `atlas run infra` or
the `infra` shim, because that is the production execution path.

## Direct Ansible Execution

Prefer `infra` for normal operator runs. If you need to bypass the wrapper while
debugging Ansible itself, use the same inventory, playbook, and vault password
file explicitly:

```bash
ANSIBLE_CONFIG=ansible.cfg ansible-playbook \
  -i inventories/kanagawa01/hosts.yml \
  playbooks/site.yml \
  --vault-password-file ./vault_pass.sh \
  --check --diff
```

For an apply, remove `--check --diff` only after reviewing the target inventory,
playbook, and limit.

## State

Daedalus does not maintain its own audit store. Atlas records script runs,
arguments, duration, and exit codes. Keep persistent operational state in Atlas or
in explicit reviewable artifacts, not in ad-hoc files inside this repository.

Local runtime directories such as `.venv/`, `.ansible/`, and `secrets/` are
machine-local and should not be used as shared state.

## Verification

There is no separate Daedalus test suite at the moment. The narrow verification
path for command-wrapper changes is:

```bash
python -m pip install -e .
infra inventory
infra check --site kanagawa01 --playbook baseline --limit kng01-recursive-dns-01
```

For documentation-only changes, inspect the rendered Markdown and confirm that the
examples still match the current `infra` CLI and repository layout.
