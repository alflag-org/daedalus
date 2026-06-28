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
  roles/
    ssh_server/
    cloudflared/
    cloudflare_ssh_target/
    systemd_resolved/
    dns_recursor/
    dns_authoritative/
    node_exporter/
    foundation/
    control/
    services/
    components/    # private service implementation details
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
- `playbooks/cloudflare.yml`: explicit host-side Cloudflare converge, outside normal `site`
- `playbooks/components/`: internal composition layers
- `roles/foundation/`: host baseline and platform roles
- `roles/control/`: Atlas control-plane roles
- `roles/services/`: service-intent roles selected by `svc_*` inventory groups
- `roles/components/`: private service implementation roles used by `roles/services/`
- top-level component roles such as `ssh_server`, `dns_recursor`, and
  `node_exporter`: host-side components selected by inventory flags

`roles/common/` and `roles/middleware/` are not active role surfaces. Their
former responsibilities have either moved into explicit `foundation/*` roles or
private `components/*` implementation roles.
