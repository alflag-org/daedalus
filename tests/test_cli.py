import inspect
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from daedalus.cli import Infra, main


class InfraCliSurfaceTest(unittest.TestCase):
    def test_public_methods_are_the_command_surface(self) -> None:
        public_methods = sorted(
            name
            for name, method in inspect.getmembers(Infra, predicate=inspect.isfunction)
            if not name.startswith("_")
        )

        self.assertEqual(
            public_methods,
            [
                "apply",
                "check",
                "diff",
                "inventory",
                "ping",
                "playbooks",
                "sites",
            ],
        )

    def test_main_exposes_infra_through_fire(self) -> None:
        with patch("daedalus.cli.fire.Fire") as fire:
            main()

        fire.assert_called_once_with(Infra)


class InfraCliDiscoveryTest(unittest.TestCase):
    def test_sites_lists_site_names_only(self) -> None:
        output = StringIO()

        with redirect_stdout(output):
            Infra().sites()

        self.assertEqual(output.getvalue().splitlines(), ["default"])

    def test_playbooks_lists_public_playbook_names_only(self) -> None:
        output = StringIO()

        with redirect_stdout(output):
            Infra().playbooks()

        self.assertEqual(
            output.getvalue().splitlines(),
            ["site", "bootstrap", "cloudflare"],
        )


class InfraCliDispatchTest(unittest.TestCase):
    def test_inventory_runs_ansible_inventory_graph(self) -> None:
        with patch("daedalus.cli.AnsibleRunner") as runner_class:
            Infra().inventory(site="default")

        runner_class.assert_called_once_with(site="default")
        runner_class.return_value.inventory_graph.assert_called_once_with()

    def test_ping_runs_ansible_ping_with_limit(self) -> None:
        with patch("daedalus.cli.AnsibleRunner") as runner_class:
            Infra().ping(limit="dns-recursive01")

        runner_class.assert_called_once_with(site="default")
        runner_class.return_value.adhoc.assert_called_once_with(
            module="ping",
            limit="dns-recursive01",
        )

    def test_check_runs_playbook_check_with_limit(self) -> None:
        with patch("daedalus.cli.AnsibleRunner") as runner_class:
            Infra().check(limit="svc_dns_recursive")

        runner_class.assert_called_once_with(site="default")
        runner_class.return_value.playbook.assert_called_once_with(
            playbook="site",
            limit="svc_dns_recursive",
            tags=None,
            skip_tags=None,
            extra_vars=None,
            check=True,
            diff=False,
        )

    def test_diff_runs_playbook_check_diff_with_limit(self) -> None:
        with patch("daedalus.cli.AnsibleRunner") as runner_class:
            Infra().diff(limit="svc_dns_recursive")

        runner_class.assert_called_once_with(site="default")
        runner_class.return_value.playbook.assert_called_once_with(
            playbook="site",
            limit="svc_dns_recursive",
            tags=None,
            skip_tags=None,
            extra_vars=None,
            check=True,
            diff=True,
        )

    def test_apply_without_yes_is_nonzero_and_does_not_run(self) -> None:
        with (
            patch("daedalus.cli.AnsibleRunner") as runner_class,
            self.assertRaises(SystemExit) as raised,
        ):
            Infra().apply(limit="svc_dns_recursive")

        self.assertEqual(str(raised.exception), "Error: apply requires --yes")
        runner_class.assert_not_called()

    def test_apply_with_yes_runs_playbook_without_check_or_diff(self) -> None:
        with patch("daedalus.cli.AnsibleRunner") as runner_class:
            Infra().apply(limit="svc_dns_recursive", yes=True)

        runner_class.assert_called_once_with(site="default")
        runner_class.return_value.playbook.assert_called_once_with(
            playbook="site",
            limit="svc_dns_recursive",
            tags=None,
            skip_tags=None,
            extra_vars=None,
            check=False,
            diff=False,
        )

    def test_apply_can_run_bootstrap_playbook_with_limit(self) -> None:
        with patch("daedalus.cli.AnsibleRunner") as runner_class:
            Infra().apply(playbook="bootstrap", limit="web02", yes=True)

        runner_class.assert_called_once_with(site="default")
        runner_class.return_value.playbook.assert_called_once_with(
            playbook="bootstrap",
            limit="web02",
            tags=None,
            skip_tags=None,
            extra_vars=None,
            check=False,
            diff=False,
        )

    def test_runtime_errors_become_system_exit(self) -> None:
        with (
            patch(
                "daedalus.cli.AnsibleRunner",
                side_effect=RuntimeError("Unknown site 'missing'"),
            ),
            self.assertRaises(SystemExit) as raised,
        ):
            Infra().inventory(site="missing")

        self.assertEqual(str(raised.exception), "Error: Unknown site 'missing'")

    def test_subprocess_failures_become_system_exit(self) -> None:
        with (
            patch("daedalus.cli.AnsibleRunner") as runner_class,
            self.assertRaises(SystemExit) as raised,
        ):
            runner_class.return_value.playbook.side_effect = (
                subprocess.CalledProcessError(returncode=4, cmd=["ansible-playbook"])
            )
            Infra().check()

        self.assertEqual(str(raised.exception), "Error: command failed with exit code 4")


class InfraFireDispatchTest(unittest.TestCase):
    def test_fire_check_command_parses_limit(self) -> None:
        with (
            patch.object(sys, "argv", ["infra", "check", "--limit", "svc_dns_recursive"]),
            patch("daedalus.cli.AnsibleRunner") as runner_class,
        ):
            main()

        runner_class.return_value.playbook.assert_called_once_with(
            playbook="site",
            limit="svc_dns_recursive",
            tags=None,
            skip_tags=None,
            extra_vars=None,
            check=True,
            diff=False,
        )

    def test_fire_diff_command_parses_limit(self) -> None:
        with (
            patch.object(sys, "argv", ["infra", "diff", "--limit", "svc_dns_recursive"]),
            patch("daedalus.cli.AnsibleRunner") as runner_class,
        ):
            main()

        runner_class.return_value.playbook.assert_called_once_with(
            playbook="site",
            limit="svc_dns_recursive",
            tags=None,
            skip_tags=None,
            extra_vars=None,
            check=True,
            diff=True,
        )

    def test_fire_apply_command_parses_playbook_limit_and_yes(self) -> None:
        with (
            patch.object(
                sys,
                "argv",
                [
                    "infra",
                    "apply",
                    "--playbook",
                    "bootstrap",
                    "--limit",
                    "web02",
                    "--yes",
                ],
            ),
            patch("daedalus.cli.AnsibleRunner") as runner_class,
        ):
            main()

        runner_class.return_value.playbook.assert_called_once_with(
            playbook="bootstrap",
            limit="web02",
            tags=None,
            skip_tags=None,
            extra_vars=None,
            check=False,
            diff=False,
        )

    def test_fire_check_command_parses_skip_tags_and_extra_vars(self) -> None:
        with (
            patch.object(
                sys,
                "argv",
                [
                    "infra",
                    "check",
                    "--limit",
                    "svc_dns_recursive",
                    "--skip_tags",
                    "bootstrap",
                    "--extra_vars",
                    "foo=bar",
                ],
            ),
            patch("daedalus.cli.AnsibleRunner") as runner_class,
        ):
            main()

        runner_class.return_value.playbook.assert_called_once_with(
            playbook="site",
            limit="svc_dns_recursive",
            tags=None,
            skip_tags="bootstrap",
            extra_vars="foo=bar",
            check=True,
            diff=False,
        )


if __name__ == "__main__":
    unittest.main()
