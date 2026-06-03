# Daedalus

Daedalus is an Atlas-operated infrastructure configuration runner for
operator-triggered Alflag host configuration management. It is an Ansible-backed
runner, not a daemon and not a general-purpose orchestration service.

```text
Daedalus = Atlas-operated infrastructure configuration runner
```

Atlas owns the script runtime, command shims, and run logs. Daedalus owns the
Ansible backend and the small `infra` command wrapper that invokes it.

## Layout

Daedalus keeps the Atlas release interface at the repository root:

```text
VERSION
commands/
modules/
requirements.txt
```

The Ansible project lives under `ansible/`:

```text
ansible/
  ansible.cfg
  inventories/
  playbooks/
  roles/
  collections/
```

Local operator support lives outside the Ansible project:

```text
tools/
secrets/
docs/
```

See [docs/layout.md](docs/layout.md) for the responsibility split. See
[docs/bootstrap-control-node.md](docs/bootstrap-control-node.md) for the first
KANAGAWA01 control node bootstrap boundary and
[docs/atlas-host.md](docs/atlas-host.md) for the Atlas host role.

## Installation

Install Daedalus as a named Atlas script release, then install the scripts
runtime and regenerate shims when needed:

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

The first KANAGAWA01 control node, `kng01-mgmt-control-01`, is manually
bootstrapped. Daedalus validates that host and can manage non-dangerous
configuration, but it does not rebuild the active Atlas runtime there by
default.

## CLI

Basic shape:

```bash
infra <action> [options]
atlas run infra <action> [options]
```

Discovery:

```bash
infra sites
infra playbooks
infra inventory --site kanagawa01
```

Reachability:

```bash
infra ping
infra ping --site kanagawa01 --limit kng01-mgmt-recdns-01
```

Dry-run validation:

```bash
infra check
infra check --site kanagawa01 --playbook baseline
infra check --site kanagawa01 --playbook baseline --limit kng01-mgmt-recdns-01
```

Diff preview:

```bash
infra diff
infra diff --site kanagawa01 --playbook baseline --limit kng01-mgmt-recdns-01
```

Apply is the mutating action and requires explicit confirmation:

```bash
infra apply --yes
infra apply --yes --site kanagawa01 --playbook baseline --limit kng01-mgmt-recdns-01
```

`check`, `diff`, and `apply` support these limited Ansible pass-through options:

```text
--limit
--tags
--skip-tags
--extra-vars
```

Before invoking Ansible, `infra` prints the exact command it will run. Unknown
sites and playbooks fail before Ansible starts.

## Configuration

Daedalus uses `ansible/ansible.cfg` and executes Ansible with `ansible/` as the
working directory. Notable defaults include:

```text
inventory = inventories/kanagawa01/hosts.yml
roles_path = roles
collections_path = collections
private_key_file = ~/.ssh/infra
remote_user = ops
vault_password_file = ../tools/vault_pass.sh
host_key_checking = False
pipelining = True
ssh_args = -o ForwardAgent=yes
```

`tools/vault_pass.sh` reads the Ansible Vault password from
`ANSIBLE_VAULT_PASSWORD` or from a local, untracked
`secrets/ansible_vault.env` file.

The steady-state connection model is `ops` plus `become`. Hosts that still need
root for their first bootstrap can override `ansible_user` in host vars
temporarily, but they should converge back to `ops` after the role has created
the account, installed `~/.ssh/infra.pub`, and granted non-interactive sudo.

Create the local secret file from the sample when needed:

```bash
cp secrets/ansible_vault.env.sample secrets/ansible_vault.env
```

Then set the value in `secrets/ansible_vault.env`:

```text
ANSIBLE_VAULT_PASSWORD=...
```

Do not commit plaintext secrets. If Vault-encrypted variable files are needed,
keep them under the site inventory that consumes them.

## Local Development

Install the Python package in editable mode when working without Atlas:

```bash
python -m pip install -e .
infra sites
infra playbooks
infra inventory
```

Runtime dependencies are in `requirements.txt`. Development-only tools are in
`requirements-dev.txt`.

## Direct Ansible Execution

Prefer `infra` for normal operator runs. If you need to bypass the wrapper while
debugging Ansible itself, execute from `ansible/` or set the config explicitly:

```bash
cd ansible
ANSIBLE_CONFIG=ansible.cfg ansible-playbook \
  -i inventories/kanagawa01/hosts.yml \
  playbooks/site.yml \
  --vault-password-file ../tools/vault_pass.sh \
  --check --diff
```

For an apply, remove `--check --diff` only after reviewing the target inventory,
playbook, and limit.

## State

Daedalus does not maintain its own audit store. Atlas records script runs,
arguments, duration, and exit codes. Keep persistent operational state in Atlas
or in explicit reviewable artifacts, not in ad-hoc files inside this repository.

Local runtime directories such as `.venv/`, `.ansible/`, and `secrets/` are
machine-local and should not be used as shared state.

## Verification

The narrow verification path for command-wrapper changes is:

```bash
python -m pip install -e .
infra sites
infra playbooks
infra inventory
infra check --site kanagawa01 --playbook baseline --limit kng01-mgmt-recdns-01
```

For documentation-only changes, inspect the rendered Markdown and confirm that
the examples match the current `infra` CLI and repository layout.
