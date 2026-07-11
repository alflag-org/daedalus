# Daedalus

Daedalus is an Atlas-operated infrastructure configuration runner for
operator-triggered Alflag host configuration management. It is an Ansible-backed
runner, not a daemon and not a general-purpose orchestration service.

```text
Daedalus = Atlas-operated infrastructure configuration runner
```

Atlas owns the script runtime, command shims, and run logs. Daedalus owns the
Ansible backend and the small `infra` command wrapper that invokes it.

## Responsibility Boundary

Daedalus is limited to the managed real-host convergence layer. Atlas owns
runtime installation, command execution, release distribution, and run logs;
Daedalus owns Ansible host state for the current managed infrastructure.

Daedalus is not a general-purpose Ansible role collection. Application-specific
operations, old experiments, and historical Minecraft, Pterodactyl, or Dify
automation belong outside this repository. Future services should be added only
when they are part of the current converge path.

The normal converge path is:

```text
foundation -> control-plane -> services
```

The accepted network zones are `CLIENT`, `MGMT`, `DMZ`, `TRANSIT`, and
`UNUSED_NATIVE`. Inventory should contain real hosts and real current network
groups only.

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
    cloudflare.yml
    components/
  roles/
    foundation/
    control/
    services/
    components/    # private service implementation details
    ssh_server/
    cloudflared/
    cloudflare_ssh_target/
    systemd_resolved/
    dns_recursor/
    dns_authoritative/
    node_exporter/
  collections/
```

Local operator support lives outside the Ansible project:

```text
tools/
docs/
```

See [docs/layout.md](docs/layout.md) for the responsibility split. See
[docs/bootstrap-control-node.md](docs/bootstrap-control-node.md) for the first
control node bootstrap boundary and
[docs/atlas-host.md](docs/atlas-host.md) for the Atlas host role. See
[docs/dns.md](docs/dns.md) for the DNS host-side management boundary and
[docs/monitoring.md](docs/monitoring.md) for the Prometheus monitoring
boundary.

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

The first control node, `control01`, is manually bootstrapped. Daedalus
validates that host and can manage non-dangerous configuration, but it does not
rebuild the active Atlas runtime there by default.

## CLI

Basic shape:

```bash
infra <command> [options]
atlas run infra <command> [options]
```

`infra` is a thin Ansible wrapper. It exposes Ansible's site, playbook, limit,
tags, skip-tags, and extra-vars concepts directly instead of adding
domain-specific commands. The CLI uses Fire, so examples use the natural long
option names from the `Infra` method signatures.

Discovery:

```bash
infra sites
infra playbooks
infra inventory
infra inventory --site default
```

`infra playbooks` lists the public playbooks:

- `site`: default steady-state converge
- `bootstrap`: first converge for a newly added Atlas-managed host
- `cloudflare`: explicit host-side Cloudflare component run

Focused component playbooks are requested explicitly with `--playbook` when a
top-level playbook exists. `cloudflare` is not imported into the normal `site`
converge because apply runs require operator-provided tunnel tokens.

Package upgrades are left to unattended-upgrades. Daedalus checks requested apt
packages with `dpkg-query` first and only invokes apt when a package is missing
or a cleanup role needs to purge an installed package. When apt is needed,
`apt_state_cache_valid_time` defaults to one day so the daily unattended
upgrade cache refresh normally prevents repeated `apt update` work during
steady-state runs.

Reachability:

```bash
infra ping
infra ping --limit dns-recursive01
infra ping --limit svc_dns_recursive
```

Dry-run validation:

```bash
infra check
infra check --limit svc_dns_recursive
infra check --playbook cloudflare --limit connector01
infra check --tags dns --limit dns-recursive01
```

Diff preview:

```bash
infra diff
infra diff --limit svc_dns_recursive
infra diff --playbook cloudflare --limit connector01
```

Apply is the mutating action and requires explicit confirmation:

```bash
infra apply --yes
infra apply --limit svc_dns_recursive --yes
infra apply --playbook bootstrap --limit web02 --yes
```

`inventory` supports:

```text
--site
```

`ping` supports:

```text
--site
--limit
```

`check`, `diff`, and `apply` support these Ansible pass-through options:

```text
--site
--playbook
--limit
--tags
--skip_tags
--extra_vars
```

The default site is `default`. The default playbook for `check`, `diff`, and
`apply` is `site`.

Before invoking Ansible, `infra` prints the exact command it will run to
stderr. Command output remains on stdout. Unknown sites and playbooks fail
before Ansible starts.

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
  `svc_mysql`, and `svc_monitoring`.

Playbooks are no longer the place where service intent is modeled. The public
playbooks only define lifecycle boundaries: `site` for steady-state converge and
`bootstrap` for first converge. Internal composition lives under
`ansible/playbooks/components/`.

## Configuration

Daedalus uses `ansible/ansible.cfg` and executes Ansible with `ansible/` as the
working directory. Notable defaults include:

```text
inventory = inventories/default/hosts.yml
roles_path = roles
collections_path = collections
private_key_file = ~/.ssh/infra
remote_user = ops
host_key_checking = False
pipelining = True
ssh_args = -C -o ControlMaster=auto -o ControlPersist=60s -o ForwardAgent=no -o IdentitiesOnly=yes -o IdentityAgent=none
```

The steady-state connection model is `ops` plus `become`. Hosts bootstrap
through the single `bootstrap` playbook, then converge back to normal
`ops`-based runs after the roles have created the account, installed
`~/.ssh/infra.pub`, and granted non-interactive sudo.

For a new host, add it to the inventory and assign at least:

- one `platform_*` group
- one `provider_*` group
- any required `cap_*` groups
- any required `svc_*` groups

That inventory declaration is the source of truth for what the host should run.

Do not commit plaintext secrets. Pass operator-only secret values from the
agreed secret store or from local files outside this repository.

The `infra` wrapper automatically loads an operator vars file for the selected
inventory when it exists:

```text
~/.config/daedalus/<site>.yml
~/.config/daedalus/<site>.yaml
~/.config/daedalus/<site>.json
```

With the default inventory selector, the path is
`~/.config/daedalus/default.yml`.
Set `DAEDALUS_OPERATOR_VARS=/path/to/vars.yml` to use a different file.
Explicit `--extra_vars` values are still supported and are passed after the
auto-loaded file.

## Local Development

Install the Python package in editable mode when working without Atlas:

```bash
python -m pip install -r requirements-dev.txt
python -m pip install -e .
python -m pytest -q
infra sites
infra playbooks
infra inventory
```

Runtime dependencies are in `requirements.txt`. Development-only tools are in
`requirements-dev.txt`.

CI runs the same Python test suite on Python 3.12 and 3.13, then performs
non-mutating Ansible playbook syntax and lint checks. To run the Ansible checks
locally:

```bash
cd ansible
ansible-galaxy collection install -r collections/requirements.yml -p collections
ansible-playbook --syntax-check playbooks/site.yml
ansible-playbook --syntax-check playbooks/bootstrap.yml
ansible-playbook --syntax-check playbooks/cloudflare.yml
ansible-lint playbooks/site.yml playbooks/bootstrap.yml playbooks/cloudflare.yml
```

## Direct Ansible Execution

Prefer `infra` for normal operator runs. The wrapper installs missing Ansible
collections from `ansible/collections/requirements.yml` before playbook runs.

If you need to bypass the wrapper while debugging Ansible itself, execute from
`ansible/` or set the config explicitly:

```bash
cd ansible
ansible-galaxy collection install -r collections/requirements.yml -p collections
ANSIBLE_CONFIG=ansible.cfg ansible-playbook \
  -i inventories/default/hosts.yml \
  playbooks/site.yml \
  --check --diff
```

For an apply, remove `--check --diff` only after reviewing the target inventory,
playbook, and limit.

Bootstrap a cloud-init VM with:

```bash
infra apply --playbook bootstrap --limit <new-host> --yes
```

Then run the steady-state converge for that host:

```bash
infra apply --limit <new-host> --yes
```

Bootstrap a root-only LXC with the same playbook, but override the first login
user for that one run:

```bash
infra apply --playbook bootstrap --limit <new-host> --yes \
  --extra_vars 'ansible_user=root ansible_become=false'
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
infra check --limit svc_dns_recursive
```

For documentation-only changes, inspect the rendered Markdown and confirm that
the examples match the current `infra` CLI and repository layout.
