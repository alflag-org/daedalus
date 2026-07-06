import re
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
LEGACY_MONITORING_NAME = "zab" + "bix"
LEGACY_MONITORING_GROUP = "svc_" + LEGACY_MONITORING_NAME
LEGACY_MONITORING_HOST = f"{LEGACY_MONITORING_NAME}01"
LEGACY_AGENT_ROLE = f"{LEGACY_MONITORING_NAME}_agent"
LEGACY_SERVICE_ROLE = f"services/{LEGACY_MONITORING_NAME}"
LEGACY_SERVER_COMPONENT = f"components/{LEGACY_MONITORING_NAME}_server"
MYSQL_GROUP = "svc_" + "mysql"
MYSQL_HOST = "mysql-shared01"


def load_yaml(path: str):
    return yaml.safe_load((REPO_ROOT / path).read_text(encoding="utf-8"))


def read_text(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def merged_inventory_hosts() -> dict[str, dict]:
    inventory = load_yaml("ansible/inventories/default/hosts.yml")
    groups = inventory["all"]["children"]["default"]["children"]
    hosts: dict[str, dict] = {}

    for group in groups.values():
        for host, values in group.get("hosts", {}).items():
            hosts.setdefault(host, {}).update(values or {})

    host_vars_dir = REPO_ROOT / "ansible" / "inventories" / "default" / "host_vars"
    for path in host_vars_dir.glob("*.yml"):
        values = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        hosts.setdefault(path.stem, {}).update(values)

    return hosts


def host_address(host: dict) -> str | None:
    return host.get("network_ipv4_address") or host.get("ansible_host")


class FoundationDnsBoundariesTest(unittest.TestCase):
    def test_workbench_is_vm_and_bastion_remains(self) -> None:
        inventory = load_yaml("ansible/inventories/default/hosts.yml")
        groups = inventory["all"]["children"]["default"]["children"]

        self.assertIn("workbench01", groups["platform_vm"]["hosts"])
        self.assertNotIn("workbench01", groups["platform_lxc"]["hosts"])
        self.assertIn("bastion01", groups["mgmt"]["hosts"])
        self.assertIn("bastion01", groups["svc_bastion"]["hosts"])

        host_vars = load_yaml(
            "ansible/inventories/default/host_vars/workbench01.yml"
        )
        self.assertEqual(host_vars["virtualization_type"], "vm")
        self.assertEqual(host_vars["network_ipv4_address"], "10.10.10.61")

        site_vars = load_yaml("ansible/inventories/default/group_vars/default.yml")
        self.assertTrue(site_vars["node_exporter_enabled"])

    def test_monitor_host_replaces_legacy_monitoring_inventory(self) -> None:
        inventory = load_yaml("ansible/inventories/default/hosts.yml")
        groups = inventory["all"]["children"]["default"]["children"]

        monitor = "monitor01"
        self.assertEqual(
            groups["mgmt"]["hosts"][monitor]["ansible_host"], "10.10.10.250"
        )
        for group in ("provider_proxmox", "platform_vm", "svc_monitoring"):
            self.assertIn(monitor, groups[group]["hosts"])

        self.assertNotIn(LEGACY_MONITORING_GROUP, groups)
        for group in groups.values():
            self.assertNotIn(LEGACY_MONITORING_HOST, group.get("hosts", {}))

        host_vars = load_yaml(
            "ansible/inventories/default/host_vars/monitor01.yml"
        )
        self.assertEqual(host_vars["hostname"], monitor)
        self.assertEqual(host_vars["network_ipv4_address"], "10.10.10.250")
        self.assertTrue(host_vars["monitoring_stack_enabled"])

    def test_shared_mysql_service_remains_independent(self) -> None:
        inventory = load_yaml("ansible/inventories/default/hosts.yml")
        groups = inventory["all"]["children"]["default"]["children"]

        self.assertIn(MYSQL_HOST, groups["mgmt"]["hosts"])
        self.assertEqual(
            groups["mgmt"]["hosts"][MYSQL_HOST]["ansible_host"],
            "10.10.10.221",
        )
        for group in ("provider_proxmox", "platform_vm", MYSQL_GROUP):
            self.assertIn(MYSQL_HOST, groups[group]["hosts"])

        host_vars = load_yaml(
            "ansible/inventories/default/host_vars/mysql-shared01.yml"
        )
        self.assertEqual(host_vars["purpose"], "shared")
        self.assertNotIn("zabbix_agent_enabled", host_vars)

        group_vars = load_yaml("ansible/inventories/default/group_vars/svc_mysql.yml")
        self.assertEqual(
            group_vars["mysql_service_intended_components"], ["mysql-server"]
        )
        self.assertEqual(group_vars["mysql_server_databases"], [])
        self.assertEqual(group_vars["mysql_server_users"], [])

    def test_dns_hosts_are_grouped_and_metadata_backed(self) -> None:
        inventory = load_yaml("ansible/inventories/default/hosts.yml")
        groups = inventory["all"]["children"]["default"]["children"]

        self.assertEqual(
            set(groups["svc_dns_recursive"]["hosts"]),
            {"dns-recursive01", "dns-recursive02"},
        )
        self.assertEqual(
            set(groups["svc_dns_authoritative"]["hosts"]),
            {
                "dns-authoritative01",
                "dns-authoritative02",
            },
        )

        expected_addresses = {
            "dns-recursive01": "10.10.10.240",
            "dns-recursive02": "10.10.10.241",
            "dns-authoritative01": "10.10.10.242",
            "dns-authoritative02": "10.10.10.243",
        }
        for host, address in expected_addresses.items():
            host_vars = load_yaml(f"ansible/inventories/default/host_vars/{host}.yml")
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
        cleanup_entries = [
            entry
            for entry in role_entries
            if entry.get("role") == "retired_monitoring_cleanup"
        ]
        node_exporter_entries = [
            entry for entry in role_entries if entry.get("role") == "node_exporter"
        ]

        self.assertEqual(
            cleanup_entries,
            [
                {
                    "role": "retired_monitoring_cleanup",
                    "when": "retired_monitoring_cleanup_enabled | default(false)",
                }
            ],
        )
        self.assertEqual(
            node_exporter_entries,
            [
                {
                    "role": "node_exporter",
                    "when": "node_exporter_enabled | default(false)",
                }
            ],
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

    def test_retired_monitoring_cleanup_removes_zabbix_artifacts(self) -> None:
        site_vars = load_yaml("ansible/inventories/default/group_vars/default.yml")
        defaults = load_yaml(
            "ansible/roles/retired_monitoring_cleanup/defaults/main.yml"
        )
        tasks = load_yaml("ansible/roles/retired_monitoring_cleanup/tasks/main.yml")
        by_name = {task["name"]: task for task in tasks}

        self.assertTrue(site_vars["retired_monitoring_cleanup_enabled"])
        self.assertIn("zabbix-agent2", defaults["retired_monitoring_cleanup_packages"])
        self.assertIn("zabbix-release", defaults["retired_monitoring_cleanup_packages"])
        self.assertIn("/etc/zabbix", defaults["retired_monitoring_cleanup_paths"])

        purge = by_name["Purge retired monitoring packages"]
        self.assertEqual(purge["ansible.builtin.include_role"]["name"], "apt_state")
        self.assertEqual(
            purge["vars"]["apt_state_packages"],
            "{{ retired_monitoring_cleanup_packages }}",
        )
        self.assertEqual(purge["vars"]["apt_state_state"], "absent")
        self.assertTrue(purge["vars"]["apt_state_purge"])
        self.assertTrue(purge["vars"]["apt_state_autoremove"])

        stop = by_name["Stop retired monitoring services"]
        self.assertIn(
            "retired_monitoring_cleanup_service.status | default('') != 'not-found'",
            stop["when"],
        )

        cleanup = by_name["Remove retired monitoring paths"]["ansible.builtin.file"]
        self.assertEqual(cleanup["state"], "absent")

    def test_services_use_private_components(self) -> None:
        mysql_tasks = read_text("ansible/roles/services/mysql/tasks/main.yml")
        monitoring_tasks = read_text("ansible/roles/services/monitoring/tasks/main.yml")

        self.assertIn("components/mysql_server", mysql_tasks)
        self.assertIn("components/prometheus", monitoring_tasks)
        self.assertIn("components/alertmanager", monitoring_tasks)
        self.assertIn("components/grafana", monitoring_tasks)
        self.assertIn("components/blackbox_exporter", monitoring_tasks)

    def test_dns_recursor_renders_internal_stub_zones(self) -> None:
        template = read_text(
            "ansible/roles/dns_recursor/templates/daedalus-recursive.conf.j2"
        )
        group_vars = load_yaml(
            "ansible/inventories/default/group_vars/svc_dns_recursive.yml"
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
                },
                {
                    "name": "access.internal",
                    "servers": ["10.10.10.242", "10.10.10.243"],
                },
            ],
        )
        self.assertEqual(
            group_vars["dns_recursor_validation_queries"],
            [
                {"name": "alflag.internal", "type": "SOA"},
                {"name": "mgmt-monitor-01.srv.alflag.internal", "type": "A"},
                {"name": "web.access.internal", "type": "A"},
            ],
        )

    def test_dns_authoritative_manages_structured_zone_contents(self) -> None:
        group_vars = load_yaml(
            "ansible/inventories/default/group_vars/svc_dns_authoritative.yml"
        )

        zones = group_vars["dns_authoritative_zones"]
        zones_by_name = {zone["name"]: zone for zone in zones}
        self.assertEqual(
            set(zones_by_name),
            {
                "alflag.internal",
                "srv.alflag.internal",
                "access.internal",
                "10.10.10.in-addr.arpa",
                "10.10.30.in-addr.arpa",
            },
        )
        self.assertNotIn("minecraft.internal", {zone["name"] for zone in zones})
        self.assertNotIn("service.internal", {zone["name"] for zone in zones})
        self.assertTrue(all(zone.get("managed") is True for zone in zones))
        self.assertTrue(all("records" in zone for zone in zones))
        self.assertTrue(all("serial" in zone for zone in zones))
        self.assertTrue(all("text" not in zone for zone in zones))
        self.assertEqual(
            zones_by_name["srv.alflag.internal"]["inventory_records"],
            "server_identity",
        )
        self.assertEqual(
            zones_by_name["access.internal"]["inventory_records"],
            "access_aliases",
        )
        self.assertEqual(
            zones_by_name["10.10.10.in-addr.arpa"]["inventory_records"],
            "reverse_ptr",
        )
        self.assertEqual(
            zones_by_name["10.10.30.in-addr.arpa"]["inventory_records"],
            "reverse_ptr",
        )
        for zone_name in (
            "srv.alflag.internal",
            "access.internal",
            "10.10.10.in-addr.arpa",
            "10.10.30.in-addr.arpa",
        ):
            self.assertEqual(zones_by_name[zone_name]["records"], [])

    def test_dns_authoritative_tasks_render_and_validate_managed_zones(self) -> None:
        tasks = load_yaml("ansible/roles/dns_authoritative/tasks/main.yml")
        by_name = {task["name"]: task for task in tasks}

        render = by_name["Render managed authoritative DNS zones"]
        self.assertIn("ansible.builtin.template", render)
        self.assertEqual(render["ansible.builtin.template"]["src"], "zone.j2")
        self.assertIn(
            "nsd-checkzone",
            render["ansible.builtin.template"]["validate"],
        )
        self.assertIn("item.managed | default(false) | bool", render["when"])

        manual_check = by_name["Check manual authoritative DNS zone files"]
        self.assertIn(
            "not (item.managed | default(false) | bool)",
            manual_check["when"],
        )
        self.assertIn("item.text is not defined", manual_check["when"])

        explicit_text = by_name["Render authoritative DNS zones from explicit text"]
        self.assertIn(
            "not (item.managed | default(false) | bool)",
            explicit_text["when"],
        )
        self.assertIn("item.text is defined", explicit_text["when"])

        self.assertIn("Require manual authoritative DNS zone files", by_name)
        self.assertIn("Validate authoritative DNS zones", by_name)

        template = read_text("ansible/roles/dns_authoritative/templates/zone.j2")
        self.assertIn("inventory_records == 'server_identity'", template)
        self.assertIn("inventory_records == 'access_aliases'", template)
        self.assertIn("inventory_records == 'reverse_ptr'", template)
        self.assertIn("hostvars[source_host]", template)
        self.assertIn("network_primary_fqdn", template)
        self.assertIn("network_service_aliases", template)

    def test_dns_authoritative_records_cover_managed_hosts(self) -> None:
        group_vars = load_yaml(
            "ansible/inventories/default/group_vars/svc_dns_authoritative.yml"
        )
        zones = {zone["name"]: zone for zone in group_vars["dns_authoritative_zones"]}
        hosts = merged_inventory_hosts()

        self.assertNotIn("minecraft.internal", zones)
        self.assertNotIn("service.internal", zones)
        self.assertNotIn("10.10.0.in-addr.arpa", zones)
        self.assertNotIn("10.255.255.in-addr.arpa", zones)
        self.assertEqual(zones["alflag.internal"]["records"], [])

        expected_srv_records = {}
        expected_access_records = {}
        expected_mgmt_ptr_records = {}
        expected_dmz_ptr_records = {}

        for host in hosts.values():
            address = host_address(host)
            fqdn = host.get("network_primary_fqdn", "").rstrip(".")
            if address and fqdn.endswith(".srv.alflag.internal"):
                expected_srv_records[
                    fqdn.removesuffix(".srv.alflag.internal")
                ] = address

                address_parts = address.split(".")
                if len(address_parts) == 4 and ".".join(address_parts[:3]) == "10.10.10":
                    expected_mgmt_ptr_records[address_parts[3]] = f"{fqdn}."
                if len(address_parts) == 4 and ".".join(address_parts[:3]) == "10.10.30":
                    expected_dmz_ptr_records[address_parts[3]] = f"{fqdn}."

            for alias in host.get("network_service_aliases", []):
                alias_name = alias.rstrip(".")
                if address and alias_name.endswith(".access.internal"):
                    expected_access_records[
                        alias_name.removesuffix(".access.internal")
                    ] = address

        self.assertEqual(
            set(expected_srv_records),
            {
                "mgmt-recdns-01",
                "mgmt-recdns-02",
                "mgmt-authdns-01",
                "mgmt-authdns-02",
                "mgmt-monitor-01",
                "mgmt-mysql-shared-01",
                "mgmt-connector-01",
                "mgmt-connector-02",
                "mgmt-bastion-01",
                "mgmt-workbench-01",
                "mgmt-control-01",
                "dmz-web-01",
            },
        )
        self.assertEqual(
            set(expected_access_records),
            {"grafana", "prometheus", "alertmanager", "mysql-shared", "web", "workbench"},
        )
        self.assertEqual(
            set(expected_mgmt_ptr_records),
            {"240", "241", "242", "243", "250", "221", "41", "42", "60", "61", "62"},
        )
        self.assertEqual(set(expected_dmz_ptr_records), {"21"})

        self.assertEqual(zones["srv.alflag.internal"]["records"], [])
        self.assertEqual(zones["access.internal"]["records"], [])
        self.assertEqual(zones["10.10.10.in-addr.arpa"]["records"], [])
        self.assertEqual(zones["10.10.30.in-addr.arpa"]["records"], [])

    def test_docs_describe_dns_and_role_boundaries(self) -> None:
        components = read_text("docs/components.md")
        layout = read_text("docs/layout.md")
        dns = read_text("docs/dns.md")

        self.assertIn("Do not duplicate DNS record values in docs", components)
        self.assertIn("private service implementation roles", layout)
        self.assertIn("Daedalus manages authoritative zone contents", dns)
        self.assertIn("Do not edit generated zone files manually", dns)

    def test_docs_do_not_duplicate_network_state(self) -> None:
        docs_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (REPO_ROOT / "docs").glob("*.md")
        )

        self.assertIsNone(
            re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?\b", docs_text)
        )
        self.assertIsNone(re.search(r"\bVLAN\s+\d+\b", docs_text))


if __name__ == "__main__":
    unittest.main()
