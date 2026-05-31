# Daedalus

Alflag のサーバ構成を管理するためのコードと運用コマンドを管理しています。
現在の構成適用は Ansible playbook を中心にしていますが、プロジェクトとしては
Ansible に限らない構成管理ツール群の置き場所です。

## Atlas 経由の実行

この repository は Atlas の script release として扱えるようにしています。
Atlas は実行入口、shim、run log を担当し、Daedalus 側の `infra`
コマンドが各構成管理ツールを呼び出します。

```bash
atlas scripts install git+https://github.com/alflag-org/daedalus.git#master --name alflag-infra
atlas scripts shims

atlas run infra inventory
atlas run infra ping
atlas run infra check
atlas run infra diff
atlas run infra apply
```

Atlas release として必要な `VERSION`、`commands/`、`modules/`、`requirements.txt`
を repository root に置いています。`commands/infra.py` が Atlas から見える
コマンド入口で、実装本体は `modules/alflag_infra` にあります。

## Local Development

```bash
python -m pip install -e .
infra inventory
infra ping
infra check
```

実行例:

```bash
infra diff --site kanagawa01 --playbook baseline
infra apply --site kanagawa01 --playbook baseline --limit kng01-recursive-dns-01
```

`infra` は既定で `site=kanagawa01`、`playbook=site` を使います。
実行前には内部で呼び出す構成管理コマンドを表示します。

Vault password は `secrets/ansible_vault.env` または `ANSIBLE_VAULT_PASSWORD`
環境変数から読み込みます。

## Ansible Vault

Ansible Vault によって、機密情報を暗号化しています。

### 暗号化

```bash
ansible-vault encrypt group_vars/all/vault
```

### 復号化

```bash
ansible-vault decrypt group_vars/all/vault
```

## Ansible playbook の直接実行

Atlas や `infra` を経由せずに Ansible playbook を直接実行する場合は、
以下のコマンドを実行します。

```bash
ansible-playbook -i hosts.yml playbook.yml --ask-vault-pass
```
