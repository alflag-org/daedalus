import os
import shlex
import subprocess
import sys
from pathlib import Path

from .paths import ansible_config_path, ansible_root, inventory_path, playbook_path


class AnsibleRunner:
    def __init__(self, site: str) -> None:
        self.site = site
        self.ansible_root = ansible_root()
        self.inventory = inventory_path(site)

    def playbook(
        self,
        playbook: str,
        limit: str | None = None,
        tags: str | None = None,
        skip_tags: str | None = None,
        extra_vars: str | None = None,
        check: bool = False,
        diff: bool = False,
    ) -> None:
        cmd = [
            "ansible-playbook",
            "-i",
            self._relative(self.inventory),
            self._relative(playbook_path(playbook)),
        ]

        self._append_limit(cmd, limit)
        self._append_option(cmd, "--tags", tags)
        self._append_option(cmd, "--skip-tags", skip_tags)
        self._append_operator_extra_vars(cmd)
        self._append_option(cmd, "--extra-vars", extra_vars)
        if check:
            cmd.append("--check")
        if diff:
            cmd.append("--diff")

        self._run(cmd)

    def adhoc(self, module: str, limit: str | None = None) -> None:
        cmd = [
            "ansible",
            "all",
            "-i",
            self._relative(self.inventory),
            "-m",
            module,
        ]

        self._append_limit(cmd, limit)
        self._run(cmd)

    def inventory_graph(self) -> None:
        cmd = [
            "ansible-inventory",
            "-i",
            self._relative(self.inventory),
            "--graph",
        ]
        self._run(cmd)

    def _run(self, cmd: list[str]) -> None:
        env = os.environ.copy()
        env["ANSIBLE_CONFIG"] = str(ansible_config_path())
        executable_dir = str(Path(sys.executable).parent)
        env["PATH"] = os.pathsep.join([executable_dir, env.get("PATH", "")])

        print(f"Running: {shlex.join(cmd)}", flush=True)
        subprocess.run(cmd, check=True, cwd=self.ansible_root, env=env)

    def _relative(self, path: Path) -> str:
        return str(path.relative_to(self.ansible_root))

    @staticmethod
    def _append_limit(cmd: list[str], limit: str | None) -> None:
        if limit and limit.strip():
            cmd.extend(["--limit", limit])

    @staticmethod
    def _append_option(cmd: list[str], option: str, value: str | None) -> None:
        if value and value.strip():
            cmd.extend([option, value])

    def _append_operator_extra_vars(self, cmd: list[str]) -> None:
        vars_path = self._operator_extra_vars_path()
        if vars_path:
            cmd.extend(["--extra-vars", f"@{vars_path}"])

    def _operator_extra_vars_path(self) -> Path | None:
        override = os.environ.get("DAEDALUS_OPERATOR_VARS")
        if override and override.strip():
            path = Path(override).expanduser()
            if not path.is_file():
                raise RuntimeError(f"Operator vars file not found: {path}")
            return path

        for suffix in ("yml", "yaml", "json"):
            path = Path.home() / ".config" / "daedalus" / f"{self.site}.{suffix}"
            if path.is_file():
                return path

        return None
