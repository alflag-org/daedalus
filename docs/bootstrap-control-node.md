# First Control Node Bootstrap

`topmost01-mgmt-control-01` is the first topmost01 control node. It is the root of
configuration management for the site and is intentionally bootstrapped by hand.

Daedalus is Atlas-operated and Ansible-backed. It needs Atlas, an Atlas scripts
runtime, Ansible, SSH material, and access to operator-managed secrets before it
can manage hosts. Making Daedalus build that first runtime from a blank host
would create a circular dependency: the configuration runner would depend on
itself before it can run.

## Role

`topmost01-mgmt-control-01` runs operator-triggered commands such as:

```bash
atlas run infra inventory --site topmost01
atlas run infra ping --site topmost01 --limit topmost01-mgmt-dns-recursive-01
atlas run infra check --site topmost01 --limit cap_control_node
```

Daedalus may validate this host and manage non-dangerous configuration on it,
but it must not rebuild or replace the active Atlas runtime by default.

Future control nodes, replacement control nodes, or control nodes in other sites
can be provisioned from an already-working control node.

## Minimal Manual Bootstrap

The first control node is expected to have at least:

- OS installation
- Network configuration
- `ops` user
- passwordless `sudo` for `ops`
- Required OS packages
- `pyenv`
- Atlas CLI
- `/etc/atlas/config.yml`
- `/etc/atlas/host.yml`
- Daedalus release installation
- Atlas scripts runtime
- `ansible-core`
- `~/.ssh/infra`

## Required Paths

- `/etc/atlas`
- `/opt/atlas`
- `/opt/atlas/tmp`
- `/var/lib/atlas`
- `/var/lib/atlas/cache/python-build`
- `/home/ops/.local/bin/atlas`
- `/home/ops/.local/share/atlas-cli-venv`
- `/home/ops/.ssh/infra`

`/opt/atlas/tmp` is the default runtime build temporary directory for this site.
`/var/lib/atlas/cache/python-build` is the default Python build cache.

## Required Secrets

Do not commit plaintext secrets.

Private SSH keys, generated credentials, and service passwords must stay out of
git. Provide service secrets from the agreed operator secret store or from
operator-local files outside the repository.

## Runtime Validation

Run these commands after manual bootstrap and after changes that affect the
runtime:

```bash
atlas status
atlas runtime status
atlas scripts list --verbose
ansible-inventory --version
atlas run infra inventory --site topmost01
atlas run infra ping --site topmost01 --limit topmost01-mgmt-dns-recursive-01
atlas run infra check --site topmost01 --limit svc_dns_recursive
atlas run infra check --site topmost01 --limit cap_control_node
atlas run infra diff --site topmost01 --limit cap_control_node
```

The first control node should be assigned to these inventory groups:

```yaml
provider_proxmox:
platform_vm:
cap_atlas_host:
cap_control_node:
```

The per-host vars remain:

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

ssh_server_enabled: true
zabbix_agent_enabled: true
```

The default `site` converge should be able to manage the control node after
bootstrap.
`atlas_bootstrap_mode: manual` records that the first install was done by hand;
it does not disable later configuration management.

For an `ops`-managed control node, make sure `ops` has passwordless `sudo` so
Ansible can apply root-owned changes non-interactively.

## Known Failure Modes

### Small `/tmp` tmpfs

Ubuntu hosts may mount `/tmp` as a small tmpfs. Python runtime builds can fail
when `/tmp` is too small.

Use:

```bash
export TMPDIR=/opt/atlas/tmp
export PYTHON_BUILD_CACHE_PATH=/var/lib/atlas/cache/python-build
```

Daedalus also writes these defaults into the `ops` profile for Atlas hosts.

### Atlas Runtime Stale Shebang

Atlas runtime install can leave console scripts with stale shebangs if a virtual
environment is built in `scripts.tmp` and then renamed to the final runtime
path.

The operational workaround is to force-reinstall runtime packages with the final
runtime Python:

```bash
/opt/atlas/runtime/python/envs/scripts/bin/python \
  -m pip install --force-reinstall ansible-core 'fire>=0.7' PyYAML
```

The permanent fix belongs in Atlas, not in Daedalus.

Atlas runtime install should:

1. Create a temporary virtual environment.
2. Rename it to the final runtime path.
3. Run `pip install` from the final runtime Python.
4. Run `pip check` from the final runtime Python.
5. Validate `bin/*` shebangs.
6. Fail closed if `scripts.tmp` appears in any console script shebang.

A longer-term design should use versioned runtime directories and a symlink
switch, for example:

```text
/opt/atlas/runtime/python/envs/scripts-<build-id>
/opt/atlas/runtime/python/envs/scripts -> scripts-<build-id>
```

That avoids mutating the active runtime in place.

### Installed Release Direct Edits

`/opt/atlas/scripts/current/daedalus` is an installed release. Direct edits under
that path are temporary and are overwritten by release updates.

Persistent changes must be committed to the Daedalus repository, then installed
or updated through Atlas.
