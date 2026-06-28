# Atlas Host Role

`atlas_host` prepares or validates hosts that participate in Atlas-operated
infrastructure management.

The role is intentionally explicit. Daedalus owns the Ansible project,
inventory, playbooks, roles, and the `infra` command wrapper. Atlas owns the
script runtime, release installation, command shims, execution logs, and host
context.

## First Control Node vs Future Control Nodes

`control01` is manually bootstrapped and already has the minimum
runtime needed to run `atlas run infra ...`.

For that host:

```yaml
ansible_connection: local
ansible_become: true
ansible_python_interpreter: /usr/bin/python3

atlas_enabled: true
atlas_bootstrap_mode: manual
atlas_role: control
atlas_runtime_kind: vm
atlas_manage_scripts: false
atlas_manage_runtime: false
atlas_validate_runtime: true
atlas_validate_shebangs: true
```

Daedalus validates the active Atlas runtime and can continue to manage the
control node after bootstrap. `atlas_bootstrap_mode: manual` records how the
host was introduced; it does not opt the host out of later configuration
management.

To manage a non-root Atlas operator account such as `ops`, the host still needs
non-interactive privilege escalation for root-owned changes.

It also does not update Atlas scripts releases by default. Running
`atlas scripts update` from inside the same active Daedalus release can replace
the directory Ansible is currently executing from, which causes Ansible to fail
after the update task with a missing file error.

Atlas hosts are now selected through the `cap_atlas_host` inventory group, and
control nodes are selected through `cap_control_node`. The public `site`
playbook imports the control-plane component internally; operators do not need a
separate Atlas-specific playbook for steady-state runs.

`control01` should declare its control-node behavior explicitly in
host vars instead of relying on a hostname-specific fallback.

Future control nodes or replacement control nodes can set management variables
from host or group variables when an already-working control node is managing
them.

## Atlas Operator Account

`atlas_host` manages Atlas under the `ops` account by default, even when the
current Ansible connection still uses `root` for bootstrap or migration work.

The role ensures:

- `ops` exists
- `ops` is in `sudo`
- `/etc/sudoers.d/90-ops` grants non-interactive sudo
- the controller's `~/.ssh/infra.pub` is present in `~ops/.ssh/authorized_keys`

That lets root-connected LXC hosts converge toward the same steady state as VM
hosts: later runs can switch to `ansible_user: ops` with `become: true`.

For a brand-new VM that already has `ops`, use the shared bootstrap playbook:

```bash
infra apply --yes --site default --playbook bootstrap --limit <new-host>
```

For a brand-new root-only LXC, use the same bootstrap playbook and override the
first login user for that run:

```bash
infra apply --yes --site default --playbook bootstrap --limit <new-host> \
  --extra-vars 'ansible_user=root ansible_become=false'
```

The playbook branches inside `foundation/bootstrap`: VM and LXC hosts share one
entrypoint, and the role selects the platform-specific `foundation/platform_*`
tasks after fact gathering. For the root-only LXC case, that run connects as
`root`, creates and authorizes `ops`, and installs passwordless sudo. After it
succeeds, switch back to the normal `site` converge.

The same public bootstrap playbook also prepares Atlas runtime hosts, but only
for inventory members of `cap_atlas_host`. Regular service hosts can use
bootstrap for operator access and platform foundation without becoming Atlas
runtime hosts.

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
atlas run infra inventory --site default
atlas run infra check --site default --limit cap_control_node
atlas run infra diff --site default --limit cap_control_node
```

For DNS LXC reachability and the service-scoped converge path:

```bash
atlas run infra ping --site default --limit dns-recursive01
atlas run infra check --site default --limit svc_dns_recursive
```
