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
        self.assertEqual(defaults["zabbix_server_mysql_schema_min_trigger_count"], 65)
        self.assertFalse(defaults["zabbix_server_recreate_partial_schema"])

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

    def test_zabbix_schema_status_checks_triggers(self) -> None:
        tasks = load_yaml("ansible/roles/middleware/zabbix-server/tasks/mysql.yml")
        schema_status = {
            task["name"]: task
            for task in tasks
        }["Check Zabbix database schema status"]["ansible.mysql.mysql_query"]

        self.assertIn("information_schema.tables", schema_status["query"])
        self.assertIn("information_schema.triggers", schema_status["query"])
        self.assertIn("trigger_count", schema_status["query"])

    def test_partial_zabbix_schema_requires_explicit_reset(self) -> None:
        tasks = load_yaml("ansible/roles/middleware/zabbix-server/tasks/mysql.yml")
        by_name = {task["name"]: task for task in tasks}

        reset = by_name["Reset partial Zabbix database schema when explicitly requested"]
        self.assertIn("zabbix_server_recreate_partial_schema | bool", reset["when"])

        validation = by_name["Validate Zabbix database schema is empty or complete"]
        self.assertIn("ansible.builtin.assert", validation)
        self.assertIn(
            "zabbix_server_mysql_schema_min_trigger_count",
            validation["ansible.builtin.assert"]["that"][0],
        )

    def test_schema_import_temporarily_trusts_function_creators(self) -> None:
        tasks = load_yaml("ansible/roles/middleware/zabbix-server/tasks/mysql.yml")
        import_block = {
            task["name"]: task
            for task in tasks
        }["Import Zabbix initial schema"]

        enable = import_block["block"][0]["ansible.mysql.mysql_query"]
        disable = import_block["always"][0]["ansible.mysql.mysql_query"]
        schema_import = import_block["block"][1]["ansible.mysql.mysql_db"]

        self.assertEqual(
            enable["query"],
            "SET GLOBAL log_bin_trust_function_creators = 1",
        )
        self.assertEqual(
            disable["query"],
            "SET GLOBAL log_bin_trust_function_creators = 0",
        )
        self.assertEqual(schema_import["state"], "import")
        self.assertEqual(schema_import["target"], "{{ zabbix_server_mysql_schema_path }}")

    def test_schema_import_validates_trigger_count(self) -> None:
        tasks = load_yaml("ansible/roles/middleware/zabbix-server/tasks/mysql.yml")
        by_name = {task["name"]: task for task in tasks}

        trigger_status = by_name["Check imported Zabbix schema trigger status"]
        self.assertIn(
            "information_schema.triggers",
            trigger_status["ansible.mysql.mysql_query"]["query"],
        )

        validation = by_name["Validate imported Zabbix schema trigger count"]
        self.assertIn(
            "zabbix_server_mysql_schema_min_trigger_count",
            validation["ansible.builtin.assert"]["that"][0],
        )


if __name__ == "__main__":
    unittest.main()
