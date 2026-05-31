# Migration Notes

Daedalus previously kept Ansible files at the repository root. They now live
under `ansible/`.

Path changes:

```text
ansible.cfg        -> ansible/ansible.cfg
inventories/      -> ansible/inventories/
playbooks/        -> ansible/playbooks/
roles/            -> ansible/roles/
group_vars/       -> ansible/inventories/kanagawa01/group_vars/ or removed when legacy-only
vault_pass.sh     -> tools/vault_pass.sh
```

The Python package was renamed from `alflag_infra` to `daedalus`. The operator
command remains `infra`.

The legacy `onp/` playbooks and the self-installing `roles/middleware/daedalus`
role were removed from the normal backend because Atlas is responsible for
installing Daedalus.

The legacy top-level `group_vars/` tree belonged to the removed root inventory
and was removed with it. Active site variables now live under
`ansible/inventories/kanagawa01/group_vars/`.
