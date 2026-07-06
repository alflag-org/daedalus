import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


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
            ["3.12", "3.13"],
        )

        run_steps = "\n".join(
            step["run"] for step in test_job["steps"] if "run" in step
        )
        self.assertIn("python -m pip install -r requirements-dev.txt", run_steps)
        self.assertIn("python -m pip install -e .", run_steps)
        self.assertIn("pytest -q", run_steps)

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


if __name__ == "__main__":
    unittest.main()
