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
        tasks = load_yaml("ansible/roles/components/mysql_server/tasks/install.yml")
        defaults = load_yaml("ansible/roles/components/mysql_server/defaults/main.yml")
        by_name = {task["name"]: task for task in tasks}

        self.assertNotIn("Set Root Password", by_name)
        self.assertIn(
            "python3-cryptography",
            defaults["mysql_server_packages"],
        )
        self.assertEqual(
            by_name["Install mysql-server"]["ansible.builtin.apt"]["name"],
            "{{ mysql_server_packages }}",
        )

        anonymous_user = by_name["Remove anonymous users"]["ansible.mysql.mysql_user"]
        self.assertEqual(anonymous_user["login_user"], "{{ mysql_login_user }}")
        self.assertEqual(
            anonymous_user["login_unix_socket"],
            "{{ mysql_login_unix_socket }}",
        )
        self.assertNotIn("login_password", anonymous_user)
        self.assertTrue(anonymous_user["host_all"])

    def test_mysql_server_manages_databases_and_users_from_variables(self) -> None:
        database_tasks = load_yaml("ansible/roles/components/mysql_server/tasks/databases.yml")
        user_tasks = load_yaml("ansible/roles/components/mysql_server/tasks/users.yml")

        database = database_tasks[0]["ansible.mysql.mysql_db"]
        user = user_tasks[0]["ansible.mysql.mysql_user"]

        self.assertEqual(database["login_user"], "{{ mysql_login_user }}")
        self.assertEqual(database["login_unix_socket"], "{{ mysql_login_unix_socket }}")
        self.assertEqual(database["name"], "{{ item.name }}")
        self.assertEqual(database["encoding"], "{{ item.encoding | default(omit) }}")
        self.assertEqual(database["collation"], "{{ item.collation | default(omit) }}")

        self.assertEqual(user["login_user"], "{{ mysql_login_user }}")
        self.assertEqual(user["login_unix_socket"], "{{ mysql_login_unix_socket }}")
        self.assertEqual(user["plugin"], "{{ item.plugin | default(omit) }}")
        self.assertEqual(
            user["plugin_auth_string"],
            "{{ item.plugin_auth_string | default(omit) }}",
        )
        self.assertNotIn("login_password", user)
        self.assertNotIn("password", user)

    def test_zabbix_workload_supplies_mysql_database_and_users(self) -> None:
        group_vars = load_yaml("ansible/inventories/kanagawa01/group_vars/svc_zabbix.yml")

        self.assertEqual(
            group_vars["mysql_server_required_secret_vars"],
            ["mysql_zabbix_password", "mysql_zabbix_monitor_password"],
        )
        self.assertEqual(
            group_vars["mysql_server_databases"],
            [
                {
                    "name": "{{ mysql_zabbix_dbname }}",
                    "encoding": "utf8mb4",
                    "collation": "utf8mb4_bin",
                }
            ],
        )

        zabbix_user, monitor_user = group_vars["mysql_server_users"]
        self.assertEqual(zabbix_user["plugin"], "{{ mysql_zabbix_auth_plugin }}")
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
        defaults = load_yaml("ansible/inventories/kanagawa01/group_vars/svc_zabbix.yml")

        self.assertEqual(defaults["mysql_zabbix_auth_plugin"], "caching_sha2_password")
        self.assertEqual(len(defaults["mysql_zabbix_password_salt"]), 20)
        self.assertEqual(len(defaults["mysql_zabbix_monitor_password_salt"]), 20)

        zabbix_defaults = load_yaml("ansible/roles/components/zabbix_server/defaults/main.yml")
        self.assertEqual(zabbix_defaults["zabbix_server_mysql_schema_min_trigger_count"], 65)
        self.assertFalse(zabbix_defaults["zabbix_server_recreate_partial_schema"])

    def test_preflight_no_longer_requires_mysql_root_password(self) -> None:
        tasks = load_yaml("ansible/roles/components/zabbix_server/tasks/preflight.yml")
        secret_check = {
            task["name"]: task
            for task in tasks
        }["Validate required Zabbix database secret variables"]

        self.assertEqual(
            secret_check["loop"],
            ["mysql_zabbix_password"],
        )

    def test_zabbix_schema_status_checks_triggers(self) -> None:
        tasks = load_yaml("ansible/roles/components/zabbix_server/tasks/mysql_schema.yml")
        schema_status = {
            task["name"]: task
            for task in tasks
        }["Check Zabbix database schema status"]["ansible.mysql.mysql_query"]

        self.assertIn("information_schema.tables", schema_status["query"])
        self.assertIn("information_schema.triggers", schema_status["query"])
        self.assertIn("trigger_count", schema_status["query"])

    def test_partial_zabbix_schema_requires_explicit_reset(self) -> None:
        tasks = load_yaml("ansible/roles/components/zabbix_server/tasks/mysql_schema.yml")
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
        tasks = load_yaml("ansible/roles/components/zabbix_server/tasks/mysql_schema.yml")
        import_block = {
            task["name"]: task
            for task in tasks
        }["Import Zabbix initial schema"]

        import_tasks = {task["name"]: task for task in import_block["block"]}
        enable = import_tasks[
            "Enable trusted function creators for Zabbix schema import"
        ]["ansible.mysql.mysql_query"]
        disable = import_block["always"][0]["ansible.mysql.mysql_query"]
        schema_import = import_tasks[
            "Import Zabbix initial schema"
        ]["ansible.mysql.mysql_db"]

        self.assertEqual(
            enable["query"],
            "SET GLOBAL log_bin_trust_function_creators = 1",
        )
        restored_query = " ".join(disable["query"].split())
        self.assertEqual(
            restored_query,
            (
                "SET GLOBAL log_bin_trust_function_creators = "
                "{{ zabbix_server_trusted_function_creators_status.query_result[0][0]."
                "log_bin_trust_function_creators | int }}"
            ),
        )
        self.assertEqual(schema_import["state"], "import")
        self.assertEqual(schema_import["target"], "{{ zabbix_server_mysql_schema_path }}")

    def test_schema_import_validates_trigger_count(self) -> None:
        tasks = load_yaml("ansible/roles/components/zabbix_server/tasks/mysql_schema.yml")
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

    def test_zabbix_role_no_longer_owns_mysql_server_configuration(self) -> None:
        tasks = load_yaml("ansible/roles/components/zabbix_server/tasks/mysql.yml")
        self.assertEqual(
            tasks,
            [
                {
                    "name": "Manage Zabbix database schema",
                    "ansible.builtin.include_tasks": {"file": "mysql_schema.yml"},
                }
            ],
        )

    def test_shared_mysql_service_is_composed_under_services(self) -> None:
        services = load_yaml("ansible/playbooks/components/services.yml")
        imports = [
            play["ansible.builtin.import_playbook"]
            for play in services
            if "ansible.builtin.import_playbook" in play
        ]
        self.assertIn("services/mysql.yml", imports)

        mysql_playbook = load_yaml("ansible/playbooks/components/services/mysql.yml")
        self.assertEqual(mysql_playbook[0]["hosts"], "svc_mysql")

        inventory = load_yaml("ansible/inventories/kanagawa01/hosts.yml")
        kanagawa01 = inventory["all"]["children"]["kanagawa01"]["children"]
        self.assertIn("kng01-mgmt-mysql-shared-01", kanagawa01["svc_mysql"]["hosts"])
        self.assertIn("kng01-mgmt-mysql-shared-01", kanagawa01["platform_vm"]["hosts"])

        group_vars = load_yaml("ansible/inventories/kanagawa01/group_vars/svc_mysql.yml")
        self.assertEqual(
            group_vars["mysql_server_bind_address"],
            "{{ network_ipv4_address | default(ansible_host) }}",
        )

        host_vars_path = (
            REPO_ROOT
            / "ansible/inventories/kanagawa01/host_vars/kng01-mgmt-mysql-shared-01.yml"
        )
        self.assertTrue(host_vars_path.is_file())
        host_vars = load_yaml(str(host_vars_path.relative_to(REPO_ROOT)))
        self.assertEqual(host_vars["hostname"], "kng01-mgmt-mysql-shared-01")

    def test_mysql_shared_host_vars_match_inventory(self) -> None:
        host_vars_path = (
            REPO_ROOT
            / "ansible/inventories/kanagawa01/host_vars/kng01-mgmt-mysql-shared-01.yml"
        )
        host_vars = load_yaml(str(host_vars_path.relative_to(REPO_ROOT)))

        self.assertEqual(host_vars_path.stem, host_vars["hostname"])
        self.assertEqual(host_vars["hostname"], "kng01-mgmt-mysql-shared-01")
        self.assertEqual(host_vars["purpose"], "shared")
        self.assertEqual(host_vars["network_ipv4_address"], "10.10.10.221")
        self.assertEqual(host_vars["network_address"], "10.10.10.221/24")
        self.assertEqual(
            host_vars["network_primary_fqdn"],
            "kng01-mgmt-mysql-shared-01.srv.alflag.internal",
        )
        self.assertIn(
            "mysql-shared.srv.alflag.internal",
            host_vars["network_service_aliases"],
        )
        self.assertNotIn(
            "mysql.alflag.internal",
            host_vars["network_service_aliases"],
        )

    def test_docs_do_not_duplicate_mysql_address_state(self) -> None:
        components = (REPO_ROOT / "docs/components.md").read_text(encoding="utf-8")
        host_vars = load_yaml(
            "ansible/inventories/kanagawa01/host_vars/kng01-mgmt-mysql-shared-01.yml"
        )

        self.assertIn("inventory vars", components)
        self.assertNotIn(host_vars["network_ipv4_address"], components)
        self.assertNotIn(host_vars["network_address"], components)
        for alias in host_vars["network_service_aliases"]:
            self.assertNotIn(alias, components)
        self.assertNotIn("mysql.alflag.internal", components)


if __name__ == "__main__":
    unittest.main()
