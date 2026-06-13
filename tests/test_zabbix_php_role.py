import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: str):
    return yaml.safe_load((REPO_ROOT / path).read_text(encoding="utf-8"))


class ZabbixPhpRoleTest(unittest.TestCase):
    def test_ubuntu_php_versions_match_supported_releases(self) -> None:
        defaults = load_yaml("ansible/roles/middleware/zabbix-server/defaults/main.yml")

        self.assertEqual(
            defaults["zabbix_server_php_versions"],
            {
                "22.04": "8.1",
                "24.04": "8.3",
                "26.04": "8.5",
            },
        )

    def test_zabbix_packages_use_selected_php_version(self) -> None:
        defaults = (
            REPO_ROOT / "ansible/roles/middleware/zabbix-server/defaults/main.yml"
        ).read_text(encoding="utf-8")

        self.assertIn('"php{{ zabbix_server_php_version }}-fpm"', defaults)
        self.assertIn('"php{{ zabbix_server_php_version }}-mysql"', defaults)
        self.assertNotIn("php8.3-fpm", defaults)

    def test_php_fpm_template_path_is_version_neutral(self) -> None:
        tasks = load_yaml("ansible/roles/middleware/zabbix-server/tasks/php-fpm.yml")
        by_name = {task["name"]: task for task in tasks}

        template = by_name["Copy 99-zabbix.ini"]["ansible.builtin.template"]
        self.assertEqual(template["src"], "./etc/php/fpm/conf.d/99-zabbix.ini")

        self.assertTrue(
            (
                REPO_ROOT
                / "ansible/roles/middleware/zabbix-server/templates/etc/php/fpm/conf.d/99-zabbix.ini"
            ).is_file()
        )


if __name__ == "__main__":
    unittest.main()
