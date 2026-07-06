import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: str):
    return yaml.safe_load((REPO_ROOT / path).read_text(encoding="utf-8"))


def iter_tasks(tasks):
    for task in tasks or []:
        yield task
        for key in ("block", "rescue", "always"):
            if key in task:
                yield from iter_tasks(task[key])


class AptStateRoleTest(unittest.TestCase):
    def test_apt_defaults_expect_unattended_upgrades_to_keep_cache_fresh(self) -> None:
        site_vars = load_yaml("ansible/inventories/default/group_vars/default.yml")

        self.assertTrue(site_vars["apt_state_update_cache"])
        self.assertEqual(site_vars["apt_state_cache_valid_time"], 86400)

    def test_roles_do_not_call_apt_directly(self) -> None:
        task_files = sorted((REPO_ROOT / "ansible" / "roles").rglob("tasks/*.yml"))

        for path in task_files:
            if "ansible/roles/apt_state/tasks" in path.as_posix():
                continue

            with self.subTest(path=path.relative_to(REPO_ROOT).as_posix()):
                for task in iter_tasks(yaml.safe_load(path.read_text(encoding="utf-8"))):
                    self.assertNotIn("ansible.builtin.apt", task)

    def test_apt_state_only_invokes_apt_when_dpkg_state_requires_it(self) -> None:
        tasks = load_yaml("ansible/roles/apt_state/tasks/main.yml")
        by_name = {task["name"]: task for task in tasks}

        check = by_name["Check requested apt packages"]
        command = check["ansible.builtin.command"]["argv"]
        self.assertIn("dpkg-query", command)
        self.assertEqual(check["changed_when"], False)
        self.assertEqual(check["failed_when"], False)
        self.assertEqual(check["check_mode"], False)

        install = by_name["Install missing apt packages"]
        apt_install = install["ansible.builtin.apt"]
        self.assertEqual(apt_install["state"], "present")
        self.assertEqual(
            apt_install["update_cache"],
            "{{ apt_state_update_cache | default(true) | bool }}",
        )
        self.assertIn(
            "apt_state_query.rc | default(1) != 0",
            install["when"],
        )

        remove = by_name["Remove installed apt packages"]
        apt_remove = remove["ansible.builtin.apt"]
        self.assertEqual(apt_remove["state"], "absent")
        self.assertEqual(
            "apt_state_query.stdout_lines | default([]) | length > 0",
            remove["when"][-1],
        )


if __name__ == "__main__":
    unittest.main()
