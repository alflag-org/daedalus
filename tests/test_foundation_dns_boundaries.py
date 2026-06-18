import re
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


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
        self.assertTrue(host_vars["zabbix_agent_enabled"])

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

    def test_foundation_applies_zabbix_agent_once(self) -> None:
        foundation = load_yaml("ansible/playbooks/components/foundation.yml")
        role_entries = foundation[0]["roles"]
        zabbix_entries = [
            entry for entry in role_entries if entry.get("role") == "zabbix_agent"
        ]

        self.assertEqual(
            zabbix_entries,
            [{"role": "zabbix_agent", "when": "zabbix_agent_enabled | default(false)"}],
        )

        for path in (
            "ansible/roles/services/mysql/tasks/main.yml",
            "ansible/roles/services/zabbix/tasks/main.yml",
        ):
            self.assertNotIn("zabbix_agent", read_text(path))

    def test_services_use_private_components(self) -> None:
        mysql_tasks = read_text("ansible/roles/services/mysql/tasks/main.yml")
        zabbix_tasks = read_text("ansible/roles/services/zabbix/tasks/main.yml")

        self.assertIn("components/mysql_server", mysql_tasks)
        self.assertIn("components/mysql_server", zabbix_tasks)
        self.assertIn("components/caddy", zabbix_tasks)
        self.assertIn("components/zabbix_server", zabbix_tasks)

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
