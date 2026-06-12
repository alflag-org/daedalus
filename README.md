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
    site.yml
    bootstrap.yml
    components/
    compat/
  roles/
    foundation/
    control/
    services/
    legacy/
    common/        # transitional implementation details
    middleware/    # transitional implementation details
  collections/
```

Local operator support lives outside the Ansible project:

```text
tools/
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

`infra playbooks` only lists the public lifecycle entrypoints:

- `site`: default steady-state converge
- `bootstrap`: first converge for a newly added Atlas-managed host

Focused component playbooks can still be requested explicitly with
`--playbook`. `atlas`, `baseline`, `dns`, `monitoring`, and `containers` remain
accepted as temporary compatibility aliases. `cloudflare` is also available as
an explicit host-side component playbook, but it is not imported into the normal
`site` converge.

Reachability:

```bash
infra ping
infra ping --site kanagawa01 --limit kng01-mgmt-recdns-01
```

Dry-run validation:

```bash
infra check
infra check --site kanagawa01 --limit cap_control_node
infra check --site kanagawa01 --limit svc_dns_recursive
```

Diff preview:

```bash
infra diff
infra diff --site kanagawa01 --limit cap_control_node
infra diff --site kanagawa01 --limit svc_dns_recursive
```

Apply is the mutating action and requires explicit confirmation:

```bash
infra apply --yes
infra apply --yes --site kanagawa01 --limit svc_dns_recursive
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

## Inventory Model

Inventory is now the primary place where host responsibility is expressed.

- `platform_*` groups select the platform foundation role, for example
  `platform_vm` and `platform_lxc`.
- `provider_*` groups describe the infrastructure provider, for example
  `provider_proxmox`.
- `cap_*` groups describe shared control-plane capabilities, for example
  `cap_atlas_host` and `cap_control_node`.
- `svc_*` groups describe service intent, for example `svc_dns_recursive`,
  `svc_dns_authoritative`, `svc_connector`, `svc_bastion`, `svc_workbench`, and
  `svc_zabbix`.

Playbooks are no longer the place where service intent is modeled. The public
playbooks only define lifecycle boundaries: `site` for steady-state converge and
`bootstrap` for first converge. Internal composition lives under
`ansible/playbooks/components/`.

## Configuration

Daedalus uses `ansible/ansible.cfg` and executes Ansible with `ansible/` as the
working directory. Notable defaults include:

```text
inventory = inventories/kanagawa01/hosts.yml
roles_path = roles
collections_path = collections
private_key_file = ~/.ssh/infra
remote_user = ops
host_key_checking = False
pipelining = True
ssh_args = -o ForwardAgent=yes
```

The steady-state connection model is `ops` plus `become`. Hosts bootstrap
through the single `bootstrap` playbook, then converge back to normal
`ops`-based runs after the roles have created the account, installed
`~/.ssh/infra.pub`, and granted non-interactive sudo.

For a new host, add it to the site inventory and assign at least:

- one `platform_*` group
- one `provider_*` group
- any required `cap_*` groups
- any required `svc_*` groups

That inventory declaration is the source of truth for what the host should run.

Do not commit plaintext secrets. Pass operator-only secret values from the
agreed secret store or from local files outside this repository.

The `infra` wrapper automatically loads a site-local operator vars file when it
exists:

```text
~/.config/daedalus/<site>.yml
~/.config/daedalus/<site>.yaml
~/.config/daedalus/<site>.json
```

For KANAGAWA01, the default path is `~/.config/daedalus/kanagawa01.yml`.
Set `DAEDALUS_OPERATOR_VARS=/path/to/vars.yml` to use a different file.
Explicit `--extra-vars` values are still supported and are passed after the
auto-loaded file.

## Local Development

Install the Python package in editable mode when working without Atlas:

```bash
python -m pip install -e .
python -m unittest discover -s tests
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
ansible-galaxy collection install -r collections/requirements.yml -p collections
ANSIBLE_CONFIG=ansible.cfg ansible-playbook \
  -i inventories/kanagawa01/hosts.yml \
  playbooks/site.yml \
  --check --diff
```

For an apply, remove `--check --diff` only after reviewing the target inventory,
playbook, and limit.

Bootstrap a cloud-init VM with:

```bash
infra apply --yes --site kanagawa01 --playbook bootstrap --limit <new-host>
```

Then run the steady-state converge for that host:

```bash
infra apply --yes --site kanagawa01 --limit <new-host>
```

Bootstrap a root-only LXC with the same playbook, but override the first login
user for that one run:

```bash
infra apply --yes --site kanagawa01 --playbook bootstrap --limit <new-host> \
  --extra-vars 'ansible_user=root ansible_become=false'
```

After that first run, use the normal `site` converge with the standard `ops`
connection model. The bootstrap playbook applies the platform foundation to
regular managed hosts. Atlas runtime setup is limited to hosts in
`cap_atlas_host`.

## State

Daedalus does not maintain its own audit store. Atlas records script runs,
arguments, duration, and exit codes. Keep persistent operational state in Atlas
or in explicit reviewable artifacts, not in ad-hoc files inside this repository.

Local runtime directories such as `.venv/` and `.ansible/` are machine-local
and should not be used as shared state.

## Verification

The narrow verification path for command-wrapper changes is:

```bash
python -m pip install -e .
infra sites
infra playbooks
infra inventory
infra check --site kanagawa01 --limit svc_dns_recursive
```

For documentation-only changes, inspect the rendered Markdown and confirm that
the examples match the current `infra` CLI and repository layout.
