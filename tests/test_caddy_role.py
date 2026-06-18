import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


class CaddyRoleTest(unittest.TestCase):
    def test_caddy_repository_uses_deb822(self) -> None:
        tasks = yaml.safe_load(
            (
                REPO_ROOT
                / "ansible"
                / "roles"
                / "components"
                / "caddy"
                / "tasks"
                / "install.yml"
            ).read_text(encoding="utf-8")
        )
        by_name = {task["name"]: task for task in tasks}

        for task in tasks:
            self.assertNotIn("ansible.builtin.apt_key", task)
            self.assertNotIn("apt_repository", task)
            self.assertNotIn("ansible.builtin.apt_repository", task)

        prerequisites = by_name["Install Caddy repository prerequisites"]
        self.assertEqual(
            prerequisites["ansible.builtin.apt"]["name"],
            ["ca-certificates", "python3-debian"],
        )

        repository = by_name["Add Caddy repository"]["ansible.builtin.deb822_repository"]
        self.assertEqual(repository["name"], "caddy-stable")
        self.assertEqual(
            repository["uris"],
            ["https://dl.cloudsmith.io/public/caddy/stable/deb/debian"],
        )
        self.assertEqual(repository["suites"], ["any-version"])
        self.assertEqual(repository["components"], ["main"])
        self.assertEqual(
            repository["signed_by"],
            "https://dl.cloudsmith.io/public/caddy/stable/gpg.key",
        )


if __name__ == "__main__":
    unittest.main()
