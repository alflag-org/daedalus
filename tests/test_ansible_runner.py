import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from daedalus.ansible import AnsibleRunner
from daedalus.cli import Infra


class AnsibleRunnerOperatorVarsTest(unittest.TestCase):
    def capture_playbook_cmd(self, runner: AnsibleRunner, **kwargs) -> list[str]:
        captured: dict[str, list[str]] = {}

        def fake_run(cmd: list[str], ensure_collections: bool = False) -> None:
            captured["cmd"] = cmd

        runner._run = fake_run  # type: ignore[method-assign]
        runner.playbook("site", **kwargs)
        return captured["cmd"]

    def test_playbook_uses_site_operator_vars_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            vars_path = Path(home) / ".config" / "daedalus" / "kanagawa01.yml"
            vars_path.parent.mkdir(parents=True)
            vars_path.write_text("mysql_zabbix_password: test\n", encoding="utf-8")

            with patch.dict(os.environ, {"HOME": home}, clear=True):
                cmd = self.capture_playbook_cmd(
                    AnsibleRunner("kanagawa01"),
                    limit="kng01-mgmt-zabbix-01",
                    check=True,
                )

        self.assertIn("--extra-vars", cmd)
        self.assertIn(f"@{vars_path}", cmd)
        self.assertLess(cmd.index(f"@{vars_path}"), cmd.index("--check"))

    def test_explicit_extra_vars_follow_operator_vars(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            vars_path = Path(home) / ".config" / "daedalus" / "kanagawa01.yml"
            vars_path.parent.mkdir(parents=True)
            vars_path.write_text("mysql_zabbix_password: test\n", encoding="utf-8")

            with patch.dict(os.environ, {"HOME": home}, clear=True):
                cmd = self.capture_playbook_cmd(
                    AnsibleRunner("kanagawa01"),
                    extra_vars="zabbix_agent_enabled=true",
                )

        extra_vars_indexes = [
            index for index, value in enumerate(cmd) if value == "--extra-vars"
        ]
        self.assertEqual(len(extra_vars_indexes), 2)
        self.assertEqual(cmd[extra_vars_indexes[0] + 1], f"@{vars_path}")
        self.assertEqual(cmd[extra_vars_indexes[1] + 1], "zabbix_agent_enabled=true")

    def test_environment_override_takes_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            default_path = Path(home) / ".config" / "daedalus" / "kanagawa01.yml"
            default_path.parent.mkdir(parents=True)
            default_path.write_text("mysql_zabbix_password: default\n", encoding="utf-8")

            override_path = Path(home) / "operator.yml"
            override_path.write_text("mysql_zabbix_password: override\n", encoding="utf-8")

            with patch.dict(
                os.environ,
                {"HOME": home, "DAEDALUS_OPERATOR_VARS": str(override_path)},
                clear=True,
            ):
                cmd = self.capture_playbook_cmd(AnsibleRunner("kanagawa01"))

        self.assertIn(f"@{override_path}", cmd)
        self.assertNotIn(f"@{default_path}", cmd)

    def test_missing_environment_override_fails(self) -> None:
        missing_path = "/tmp/daedalus-missing-vars.yml"

        with patch.dict(
            os.environ,
            {"DAEDALUS_OPERATOR_VARS": missing_path},
            clear=True,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                f"Operator vars file not found: {missing_path}",
            ):
                AnsibleRunner("kanagawa01").playbook("site")


class AnsibleRunnerCollectionsTest(unittest.TestCase):
    def build_runner(self, ansible_root: Path) -> AnsibleRunner:
        runner = AnsibleRunner("kanagawa01")
        runner.ansible_root = ansible_root
        return runner

    def write_requirements(self, ansible_root: Path) -> None:
        collections = ansible_root / "collections"
        collections.mkdir(parents=True)
        (collections / "requirements.yml").write_text(
            "---\ncollections:\n  - name: ansible.mysql\n    version: '>=3.10.0'\n",
            encoding="utf-8",
        )

    def install_collection(self, ansible_root: Path, version: str = "3.10.0") -> None:
        collection_path = (
            ansible_root
            / "collections"
            / "ansible_collections"
            / "ansible"
            / "mysql"
        )
        collection_path.mkdir(parents=True)
        (collection_path / "MANIFEST.json").write_text(
            f'{{"collection_info": {{"version": "{version}"}}}}\n',
            encoding="utf-8",
        )

    def test_playbook_enables_collection_check(self) -> None:
        runner = AnsibleRunner("kanagawa01")

        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(runner, "_run") as run,
        ):
            runner.playbook("site")

        run.assert_called_once()
        self.assertTrue(run.call_args.kwargs["ensure_collections"])

    def test_inventory_graph_skips_collection_check(self) -> None:
        runner = AnsibleRunner("kanagawa01")

        with patch.object(runner, "_run") as run:
            runner.inventory_graph()

        run.assert_called_once()
        self.assertEqual(run.call_args.kwargs, {})

    def test_missing_collection_is_detected_from_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            ansible_root = Path(tempdir)
            self.write_requirements(ansible_root)

            runner = self.build_runner(ansible_root)

            self.assertEqual(runner._missing_collections(), ["ansible.mysql"])

    def test_outdated_collection_is_reported_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            ansible_root = Path(tempdir)
            self.write_requirements(ansible_root)
            self.install_collection(ansible_root, version="3.9.9")

            runner = self.build_runner(ansible_root)

            self.assertEqual(runner._missing_collections(), ["ansible.mysql"])

    def test_installed_collection_is_not_reported_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            ansible_root = Path(tempdir)
            self.write_requirements(ansible_root)
            self.install_collection(ansible_root)

            runner = self.build_runner(ansible_root)

            self.assertEqual(runner._missing_collections(), [])

    def test_missing_collection_installs_requirements_before_run(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            ansible_root = Path(tempdir)
            self.write_requirements(ansible_root)

            runner = self.build_runner(ansible_root)
            env = {"ANSIBLE_CONFIG": str(ansible_root / "ansible.cfg")}

            with (
                patch("builtins.print"),
                patch("daedalus.ansible.subprocess.run") as run,
            ):
                runner._ensure_collections(env)

        run.assert_called_once_with(
            [
                "ansible-galaxy",
                "collection",
                "install",
                "--timeout",
                "30",
                "--upgrade",
                "-r",
                "collections/requirements.yml",
                "-p",
                "collections",
            ],
            check=True,
            cwd=ansible_root,
            env=env,
            timeout=120,
        )

    def test_collection_install_timeout_reports_runtime_error(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            ansible_root = Path(tempdir)
            self.write_requirements(ansible_root)

            runner = self.build_runner(ansible_root)

            with (
                patch("builtins.print"),
                patch(
                    "daedalus.ansible.subprocess.run",
                    side_effect=subprocess.TimeoutExpired(
                        cmd="ansible-galaxy",
                        timeout=120,
                    ),
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "Timed out installing Ansible collections from "
                    "collections/requirements.yml",
                ):
                    runner._ensure_collections({})

    def test_installed_collection_skips_requirements_install(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            ansible_root = Path(tempdir)
            self.write_requirements(ansible_root)
            self.install_collection(ansible_root)

            runner = self.build_runner(ansible_root)

            with patch("daedalus.ansible.subprocess.run") as run:
                runner._ensure_collections({})

        run.assert_not_called()


class InfraPlaybooksTest(unittest.TestCase):
    def test_playbooks_lists_public_entrypoints(self) -> None:
        output = StringIO()

        with redirect_stdout(output):
            Infra().playbooks()

        self.assertEqual(
            output.getvalue().splitlines(),
            ["site", "bootstrap", "cloudflare"],
        )


if __name__ == "__main__":
    unittest.main()
