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
  roles/
  collections/
```

Local operator support stays outside the Ansible project:

```text
tools/
secrets/
docs/
```

This split keeps Atlas packaging concerns separate from the Ansible project. New
backends should not be added beside `playbooks/` and `roles/` at the repository
root.
