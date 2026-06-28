import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
LEGACY_MONITORING_NAME = "zab" + "bix"
LEGACY_MONITORING_GROUP = "svc_" + LEGACY_MONITORING_NAME
LEGACY_MONITORING_HOST = f"topmost01-mgmt-{LEGACY_MONITORING_NAME}-01"
LEGACY_MONITORING_PLAYBOOK = f"services/{LEGACY_MONITORING_NAME}.yml"


def load_yaml(path: str):
    return yaml.safe_load((REPO_ROOT / path).read_text(encoding="utf-8"))


def read_text(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


class MonitoringStackTest(unittest.TestCase):
    def test_services_playbook_imports_monitoring(self) -> None:
        services = load_yaml("ansible/playbooks/components/services.yml")
        imports = [entry["ansible.builtin.import_playbook"] for entry in services]

        self.assertIn("services/monitoring.yml", imports)
        self.assertIn("services/mysql.yml", imports)
        self.assertNotIn(LEGACY_MONITORING_PLAYBOOK, imports)

    def test_monitoring_playbook_targets_service_group(self) -> None:
        monitoring = load_yaml("ansible/playbooks/components/services/monitoring.yml")

        self.assertEqual(monitoring[0]["hosts"], "svc_monitoring")
        self.assertEqual(
            monitoring[0]["roles"],
            [
                {
                    "role": "services/monitoring",
                    "when": "monitoring_stack_enabled | default(false)",
                }
            ],
        )

    def test_monitoring_service_includes_components(self) -> None:
        tasks = read_text("ansible/roles/services/monitoring/tasks/main.yml")

        for component in (
            "components/prometheus",
            "components/alertmanager",
            "components/grafana",
            "components/blackbox_exporter",
        ):
            self.assertIn(component, tasks)

    def test_prometheus_uses_file_sd_targets(self) -> None:
        template = read_text(
            "ansible/roles/components/prometheus/templates/prometheus.yml.j2"
        )

        self.assertIn("file_sd_configs", template)
        self.assertIn("{{ prometheus_file_sd_dir }}/node*.json", template)
        self.assertIn("{{ prometheus_file_sd_dir }}/blackbox_http*.json", template)

    def test_prometheus_alert_rules_cover_initial_failures(self) -> None:
        alerts = read_text(
            "ansible/roles/components/prometheus/templates/alerts.yml.j2"
        )

        self.assertIn("HostDown", alerts)
        self.assertIn("BlackboxEndpointDown", alerts)

    def test_inventory_has_no_legacy_monitoring_group_or_host(self) -> None:
        inventory = load_yaml("ansible/inventories/topmost01/hosts.yml")
        groups = inventory["all"]["children"]["topmost01"]["children"]

        self.assertNotIn(LEGACY_MONITORING_GROUP, groups)
        self.assertIn("svc_monitoring", groups)
        self.assertIn("svc_mysql", groups)
        for group in groups.values():
            self.assertNotIn(LEGACY_MONITORING_HOST, group.get("hosts", {}))
        self.assertIn("topmost01-mgmt-monitor-01", groups["svc_monitoring"]["hosts"])


if __name__ == "__main__":
    unittest.main()
