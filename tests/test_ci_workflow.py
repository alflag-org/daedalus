import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKOUT_ACTION = "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683"
MISE_ACTION = "jdx/mise-action@e6a8b3978addb5a52f2b4cd9d91eafa7f0ab959d"


def load_workflow() -> dict:
    return yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )


class CiWorkflowTest(unittest.TestCase):
    def test_ci_runs_on_pull_requests_and_master_pushes(self) -> None:
        workflow = load_workflow()

        self.assertIn("pull_request", workflow["on"])
        self.assertEqual(workflow["on"]["push"]["branches"], ["master"])

    def test_test_job_runs_pytest_on_supported_python_versions(self) -> None:
        test_job = load_workflow()["jobs"]["test"]

        self.assertEqual(
            test_job["strategy"]["matrix"]["python-version"],
            ["3.12.13", "3.13.14"],
        )

        run_steps = "\n".join(
            step["run"] for step in test_job["steps"] if "run" in step
        )
        self.assertIn("python -m pip install -r requirements-dev.txt", run_steps)
        self.assertIn("python -m pip install -e .", run_steps)
        self.assertIn("pytest -q", run_steps)
        self.assertIn("git diff --exit-code -- mise.toml mise.lock", run_steps)

    def test_jobs_install_tools_with_pinned_actions(self) -> None:
        jobs = load_workflow()["jobs"]

        for job in jobs.values():
            actions = [step["uses"] for step in job["steps"] if "uses" in step]
            self.assertIn(CHECKOUT_ACTION, actions)
            self.assertIn(MISE_ACTION, actions)
            self.assertFalse(
                any(action.startswith("actions/setup-python@") for action in actions)
            )

    def test_ansible_syntax_job_checks_public_playbooks(self) -> None:
        syntax_job = load_workflow()["jobs"]["ansible-syntax"]
        run_steps = "\n".join(
            step["run"] for step in syntax_job["steps"] if "run" in step
        )

        self.assertIn(
            "ansible-galaxy collection install -r collections/requirements.yml -p collections",
            run_steps,
        )
        for playbook in (
            "playbooks/site.yml",
            "playbooks/bootstrap.yml",
            "playbooks/cloudflare.yml",
        ):
            self.assertIn(f"ansible-playbook --syntax-check {playbook}", run_steps)

    def test_ansible_syntax_job_runs_ansible_lint(self) -> None:
        syntax_job = load_workflow()["jobs"]["ansible-syntax"]
        run_steps = "\n".join(
            step["run"] for step in syntax_job["steps"] if "run" in step
        )

        self.assertIn(
            "ansible-lint playbooks/site.yml playbooks/bootstrap.yml playbooks/cloudflare.yml",
            run_steps,
        )
        self.assertIn(
            'actionlint -shellcheck="$(command -v shellcheck)" .github/workflows/*.yml',
            run_steps,
        )


if __name__ == "__main__":
    unittest.main()
