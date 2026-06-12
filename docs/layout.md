# Repository Layout

Daedalus has three separate areas.

The Atlas release interface stays at the repository root:

```text
VERSION
commands/
modules/
requirements.txt
```

The Ansible backend is self-contained under `ansible/`:

```text
ansible/
  ansible.cfg
  inventories/
  playbooks/
    site.yml
    bootstrap.yml
    cloudflare.yml
    components/
    compat/
  roles/
    ssh_server/
    cloudflared/
    cloudflare_ssh_target/
    systemd_resolved/
    dns_recursor/
    dns_authoritative/
    zabbix_agent/
    docker_host/
    vector_agent/
    foundation/
    control/
    services/
    legacy/
    common/        # transitional implementation details
    middleware/    # transitional implementation details
  collections/
```

Local operator support stays outside the Ansible project:

```text
tools/
docs/
```

This split keeps Atlas packaging concerns separate from the Ansible project. New
backends should not be added beside `playbooks/` and `roles/` at the repository
root.

Within `ansible/`, the boundaries are:

- `inventories/`: source of truth for host responsibility and group membership
- `playbooks/site.yml`: steady-state site converge entrypoint
- `playbooks/bootstrap.yml`: first converge entrypoint for new Atlas-managed hosts
- `playbooks/components/`: internal composition layers
- `playbooks/compat/`: temporary compatibility aliases for deprecated playbook names
- `roles/foundation/`: host baseline and platform roles
- `roles/control/`: Atlas control-plane roles
- `roles/services/`: service-intent roles selected by `svc_*` inventory groups
- `roles/<component>/`: component implementation roles selected by host vars
- `roles/legacy/`: controller-local or not-yet-migrated roles excluded from normal site converge
