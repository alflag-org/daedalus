import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: str):
    return yaml.safe_load((REPO_ROOT / path).read_text(encoding="utf-8"))


class ZabbixMysqlRolesTest(unittest.TestCase):
    def test_collection_requirement_uses_ansible_mysql(self) -> None:
        requirements = load_yaml("ansible/collections/requirements.yml")

        self.assertEqual(
            requirements["collections"],
            [{"name": "ansible.mysql", "version": ">=3.10.0"}],
        )

    def test_mysql_server_uses_socket_root_management(self) -> None:
        tasks = load_yaml("ansible/roles/middleware/mysql-server/tasks/install.yml")
        by_name = {task["name"]: task for task in tasks}

        self.assertNotIn("Set Root Password", by_name)
        self.assertIn(
            "python3-cryptography",
            by_name["Install mysql-server"]["ansible.builtin.apt"]["name"],
        )

        anonymous_user = by_name["Remove anonymous users"]["ansible.mysql.mysql_user"]
        self.assertEqual(anonymous_user["login_user"], "root")
        self.assertEqual(
            anonymous_user["login_unix_socket"],
            "{{ mysql_login_unix_socket }}",
        )
        self.assertNotIn("login_password", anonymous_user)
        self.assertTrue(anonymous_user["host_all"])

    def test_zabbix_mysql_users_use_caching_sha2_password(self) -> None:
        tasks = load_yaml("ansible/roles/middleware/zabbix-server/tasks/mysql.yml")
        by_name = {task["name"]: task for task in tasks}

        zabbix_user = by_name["Create Zabbix User"]["ansible.mysql.mysql_user"]
        monitor_user = by_name["Create zabbix_monitor User"]["ansible.mysql.mysql_user"]

        for user in (zabbix_user, monitor_user):
            self.assertEqual(user["login_user"], "root")
            self.assertEqual(user["plugin"], "{{ mysql_zabbix_auth_plugin }}")
            self.assertNotIn("login_password", user)
            self.assertNotIn("password", user)

        self.assertEqual(zabbix_user["plugin_auth_string"], "{{ mysql_zabbix_password }}")
        self.assertEqual(zabbix_user["salt"], "{{ mysql_zabbix_password_salt }}")
        self.assertEqual(
            monitor_user["plugin_auth_string"],
            "{{ mysql_zabbix_monitor_password }}",
        )
        self.assertEqual(
            monitor_user["salt"],
            "{{ mysql_zabbix_monitor_password_salt }}",
        )

    def test_zabbix_mysql_defaults_use_valid_auth_salts(self) -> None:
        defaults = load_yaml("ansible/roles/middleware/zabbix-server/defaults/main.yml")

        self.assertEqual(defaults["mysql_zabbix_auth_plugin"], "caching_sha2_password")
        self.assertEqual(len(defaults["mysql_zabbix_password_salt"]), 20)
        self.assertEqual(len(defaults["mysql_zabbix_monitor_password_salt"]), 20)

    def test_preflight_no_longer_requires_mysql_root_password(self) -> None:
        tasks = load_yaml("ansible/roles/middleware/zabbix-server/tasks/preflight.yml")
        secret_check = {
            task["name"]: task
            for task in tasks
        }["Validate required Zabbix database secret variables"]

        self.assertEqual(
            secret_check["loop"],
            ["mysql_zabbix_password", "mysql_zabbix_monitor_password"],
        )


if __name__ == "__main__":
    unittest.main()
