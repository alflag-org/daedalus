# Atlas Host Role

`atlas_host` prepares or validates hosts that participate in Atlas-operated
infrastructure management.

The role is intentionally explicit. Daedalus owns the Ansible project,
inventory, playbooks, roles, and the `infra` command wrapper. Atlas owns the
script runtime, release installation, command shims, execution logs, and host
context.

## First Control Node vs Future Control Nodes

`kng01-mgmt-control-01` is manually bootstrapped and already has the minimum
runtime needed to run `atlas run infra ...`.

For that host:

```yaml
atlas_role: control
atlas_manage_scripts: false
atlas_manage_runtime: false
atlas_validate_runtime: true
```

Daedalus validates the active Atlas runtime and renders expected configuration,
but it does not rebuild the active runtime by default.

It also does not update Atlas scripts releases by default. Running
`atlas scripts update` from inside the same active Daedalus release can replace
the directory Ansible is currently executing from, which causes Ansible to fail
after the update task with a missing file error.

The `atlas.yml` playbook now applies `atlas_host` to Atlas hosts by default.
Hosts that should be excluded can opt out with `atlas_enabled: false`.

`kng01-mgmt-control-01` should declare its control-node behavior explicitly in
host vars instead of relying on a hostname-specific fallback.

Future control nodes or replacement control nodes can set management variables
from host or group variables when an already-working control node is managing
them.

## Scripts Release Management

`atlas_manage_scripts` controls whether the role runs:

```bash
atlas scripts update
```

The default is `false`. Keep it disabled on a host that is currently running
Daedalus from `/opt/atlas/scripts/current/daedalus`.

## Runtime Management

`atlas_manage_runtime` controls whether the role runs:

```bash
atlas runtime install
```

The default is `false` to avoid replacing the first manually bootstrapped
runtime by accident.

When runtime management is enabled, the role also force-reinstalls runtime
packages with the final runtime Python as a workaround for stale console-script
shebangs.

## Runtime Validation

`atlas_validate_runtime` controls checks that require a working Atlas scripts
runtime. The default is `false`, because fresh hosts do not have the Atlas
runtime yet:

- `atlas runtime status`
- runtime `ansible-inventory --version`
- optional shebang validation

`atlas_validate_shebangs` controls the shebang check. It defaults to `true`.

## Temporary Directory Policy

Atlas runtime builds should not rely on `/tmp`. Some Ubuntu hosts use a small
tmpfs there.

Daedalus uses:

```text
TMPDIR=/opt/atlas/tmp
PYTHON_BUILD_CACHE_PATH=/var/lib/atlas/cache/python-build
```

The role creates those directories and writes the environment policy to the
Atlas operator user's profile.

## Rendered Configuration

The role renders:

- `/etc/atlas/config.yml`
- `/etc/atlas/host.yml`

The default Daedalus release source is:

```yaml
atlas_releases:
  daedalus:
    source: daedalus

atlas_registries:
  daedalus:
    source: "git+https://github.com/alflag-org/daedalus.git#master"
```

## Validation Commands

Use the wrapper through Atlas on the control node:

```bash
atlas run infra inventory --site kanagawa01
atlas run infra check --site kanagawa01 --playbook atlas --limit kng01-mgmt-control-01
atlas run infra diff --site kanagawa01 --playbook atlas --limit kng01-mgmt-control-01
```

For DNS LXC reachability and the conservative baseline role:

```bash
atlas run infra ping --site kanagawa01 --limit kng01-mgmt-recdns-01
atlas run infra check --site kanagawa01 --playbook baseline --limit kng01-mgmt-recdns-01
```
