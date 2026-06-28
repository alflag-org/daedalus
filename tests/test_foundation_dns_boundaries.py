import re
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
LEGACY_MONITORING_NAME = "zab" + "bix"
LEGACY_MONITORING_GROUP = "svc_" + LEGACY_MONITORING_NAME
LEGACY_MONITORING_HOST = f"kng01-mgmt-{LEGACY_MONITORING_NAME}-01"
LEGACY_AGENT_ROLE = f"{LEGACY_MONITORING_NAME}_agent"
LEGACY_SERVICE_ROLE = f"services/{LEGACY_MONITORING_NAME}"
LEGACY_SERVER_COMPONENT = f"components/{LEGACY_MONITORING_NAME}_server"
LEGACY_MYSQL_GROUP = "svc_" + "mysql"
LEGACY_MYSQL_HOST = "kng01-mgmt-" + "mysql-shared-01"


def load_yaml(path: str):
    return yaml.safe_load((REPO_ROOT / path).read_text(encoding="utf-8"))


def read_text(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


class FoundationDnsBoundariesTest(unittest.TestCase):
    def test_workbench_is_vm_and_bastion_remains(self) -> None:
        inventory = load_yaml("ansible/inventories/kanagawa01/hosts.yml")
        groups = inventory["all"]["children"]["kanagawa01"]["children"]

        self.assertIn("kng01-mgmt-workbench-01", groups["platform_vm"]["hosts"])
        self.assertNotIn("kng01-mgmt-workbench-01", groups["platform_lxc"]["hosts"])
        self.assertIn("kng01-mgmt-bastion-01", groups["kng01_mgmt"]["hosts"])
        self.assertIn("kng01-mgmt-bastion-01", groups["svc_bastion"]["hosts"])

        host_vars = load_yaml(
            "ansible/inventories/kanagawa01/host_vars/kng01-mgmt-workbench-01.yml"
        )
        self.assertEqual(host_vars["virtualization_type"], "vm")
        self.assertEqual(host_vars["network_ipv4_address"], "10.10.10.61")

        site_vars = load_yaml("ansible/inventories/kanagawa01/group_vars/kanagawa01.yml")
        self.assertTrue(site_vars["node_exporter_enabled"])

    def test_monitor_host_replaces_legacy_monitoring_inventory(self) -> None:
        inventory = load_yaml("ansible/inventories/kanagawa01/hosts.yml")
        groups = inventory["all"]["children"]["kanagawa01"]["children"]

        monitor = "kng01-mgmt-monitor-01"
        self.assertEqual(groups["kng01_mgmt"]["hosts"][monitor]["ansible_host"], "10.10.10.250")
        for group in ("provider_proxmox", "platform_vm", "svc_monitoring"):
            self.assertIn(monitor, groups[group]["hosts"])

        self.assertNotIn(LEGACY_MONITORING_GROUP, groups)
        for group in groups.values():
            self.assertNotIn(LEGACY_MONITORING_HOST, group.get("hosts", {}))

        host_vars = load_yaml(
            "ansible/inventories/kanagawa01/host_vars/kng01-mgmt-monitor-01.yml"
        )
        self.assertEqual(host_vars["hostname"], monitor)
        self.assertEqual(host_vars["network_ipv4_address"], "10.10.10.250")
        self.assertTrue(host_vars["monitoring_stack_enabled"])

    def test_shared_mysql_service_remains_independent(self) -> None:
        inventory = load_yaml("ansible/inventories/kanagawa01/hosts.yml")
        groups = inventory["all"]["children"]["kanagawa01"]["children"]

        self.assertIn(LEGACY_MYSQL_HOST, groups["kng01_mgmt"]["hosts"])
        self.assertEqual(
            groups["kng01_mgmt"]["hosts"][LEGACY_MYSQL_HOST]["ansible_host"],
            "10.10.10.221",
        )
        for group in ("provider_proxmox", "platform_vm", LEGACY_MYSQL_GROUP):
            self.assertIn(LEGACY_MYSQL_HOST, groups[group]["hosts"])

        host_vars = load_yaml(
            "ansible/inventories/kanagawa01/host_vars/kng01-mgmt-mysql-shared-01.yml"
        )
        self.assertEqual(host_vars["purpose"], "shared")
        self.assertNotIn("zabbix_agent_enabled", host_vars)

        group_vars = load_yaml("ansible/inventories/kanagawa01/group_vars/svc_mysql.yml")
        self.assertEqual(group_vars["mysql_service_intended_components"], ["mysql-server"])
        self.assertEqual(group_vars["mysql_server_databases"], [])
        self.assertEqual(group_vars["mysql_server_users"], [])

    def test_dns_hosts_are_grouped_and_metadata_backed(self) -> None:
        inventory = load_yaml("ansible/inventories/kanagawa01/hosts.yml")
        groups = inventory["all"]["children"]["kanagawa01"]["children"]

        self.assertEqual(
            set(groups["svc_dns_recursive"]["hosts"]),
            {"kng01-mgmt-recdns-01", "kng01-mgmt-recdns-02"},
        )
        self.assertEqual(
            set(groups["svc_dns_authoritative"]["hosts"]),
            {"kng01-mgmt-authdns-01", "kng01-mgmt-authdns-02"},
        )

        expected_addresses = {
            "kng01-mgmt-recdns-01": "10.10.10.240",
            "kng01-mgmt-recdns-02": "10.10.10.241",
            "kng01-mgmt-authdns-01": "10.10.10.242",
            "kng01-mgmt-authdns-02": "10.10.10.243",
        }
        for host, address in expected_addresses.items():
            host_vars = load_yaml(f"ansible/inventories/kanagawa01/host_vars/{host}.yml")
            self.assertEqual(host_vars["hostname"], host)
            self.assertEqual(host_vars["network_ipv4_address"], address)
            self.assertIn("network_primary_fqdn", host_vars)

    def test_active_roles_do_not_reference_legacy_common_or_middleware(self) -> None:
        active_text = "\n".join(
            path.read_text(encoding="utf-8")
            for root in ("ansible/playbooks", "ansible/roles")
            for path in (REPO_ROOT / root).rglob("*")
            if path.is_file()
        )

        for legacy_ref in (
            "common/vm",
            "common/lxc",
            "common/bootstrap",
            "common/operator",
            "middleware/",
        ):
            self.assertNotIn(legacy_ref, active_text)

    def test_foundation_applies_node_exporter_once(self) -> None:
        foundation = load_yaml("ansible/playbooks/components/foundation.yml")
        role_entries = foundation[0]["roles"]
        node_exporter_entries = [
            entry for entry in role_entries if entry.get("role") == "node_exporter"
        ]

        self.assertEqual(
            node_exporter_entries,
            [{"role": "node_exporter", "when": "node_exporter_enabled | default(false)"}],
        )

        active_text = "\n".join(
            path.read_text(encoding="utf-8")
            for root in ("ansible/playbooks", "ansible/roles")
            for path in (REPO_ROOT / root).rglob("*")
            if path.is_file()
        )
        for removed_ref in (
            LEGACY_AGENT_ROLE,
            LEGACY_SERVICE_ROLE,
            LEGACY_SERVER_COMPONENT,
        ):
            self.assertNotIn(removed_ref, active_text)

    def test_services_use_private_components(self) -> None:
        mysql_tasks = read_text("ansible/roles/services/mysql/tasks/main.yml")
        monitoring_tasks = read_text("ansible/roles/services/monitoring/tasks/main.yml")

        self.assertIn("components/mysql_server", mysql_tasks)
        self.assertIn("components/prometheus", monitoring_tasks)
        self.assertIn("components/alertmanager", monitoring_tasks)
        self.assertIn("components/grafana", monitoring_tasks)
        self.assertIn("components/blackbox_exporter", monitoring_tasks)

    def test_dns_recursor_renders_internal_stub_zones(self) -> None:
        template = read_text("ansible/roles/dns_recursor/templates/daedalus-recursive.conf.j2")
        group_vars = load_yaml(
            "ansible/inventories/kanagawa01/group_vars/svc_dns_recursive.yml"
        )

        self.assertIn("stub-zone:", template)
        self.assertIn("stub-addr: {{ server }}", template)
        self.assertIn("forward-zone:", template)
        self.assertEqual(
            group_vars["dns_recursor_allowed_cidrs"],
            ["10.10.0.0/24", "10.10.10.0/24", "10.10.30.0/24"],
        )
        self.assertEqual(
            group_vars["dns_recursor_stub_zones"],
            [
                {
                    "name": "alflag.internal",
                    "servers": ["10.10.10.242", "10.10.10.243"],
                }
            ],
        )

    def test_dns_authoritative_keeps_zone_text_manual(self) -> None:
        tasks = load_yaml("ansible/roles/dns_authoritative/tasks/main.yml")
        by_name = {task["name"]: task for task in tasks}
        group_vars = load_yaml(
            "ansible/inventories/kanagawa01/group_vars/svc_dns_authoritative.yml"
        )

        render = by_name["Render authoritative DNS zones from explicit text"]
        self.assertIn("item.text is defined", render["when"])
        self.assertIn("content", render["ansible.builtin.copy"])

        self.assertIn("Require manual authoritative DNS zone files", by_name)
        self.assertIn("Validate authoritative DNS zones", by_name)
        self.assertEqual(
            group_vars["dns_authoritative_zones"],
            [{"name": "alflag.internal", "file": "/etc/nsd/zones/alflag.internal.zone"}],
        )
        self.assertNotIn("text", group_vars["dns_authoritative_zones"][0])

    def test_docs_describe_dns_and_role_boundaries(self) -> None:
        components = read_text("docs/components.md")
        layout = read_text("docs/layout.md")
        dns = read_text("docs/dns.md")

        self.assertIn("Do not duplicate DNS record values in docs", components)
        self.assertIn("private service implementation roles", layout)
        self.assertIn("Authoritative zone record contents remain manual", dns)

    def test_docs_do_not_duplicate_network_state(self) -> None:
        docs_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (REPO_ROOT / "docs").glob("*.md")
        )

        self.assertIsNone(re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?\b", docs_text))
        self.assertIsNone(re.search(r"\bVLAN\s+\d+\b", docs_text))


if __name__ == "__main__":
    unittest.main()
