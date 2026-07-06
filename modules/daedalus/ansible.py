import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

from .paths import ansible_config_path, ansible_root, inventory_path, playbook_path


GALAXY_INSTALL_TIMEOUT_SECONDS = 120
GALAXY_SERVER_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class CollectionRequirement:
    name: str
    version: str | None = None


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

        self._run(cmd, ensure_collections=True)

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

    def _run(self, cmd: list[str], ensure_collections: bool = False) -> None:
        env = self._ansible_env()

        if ensure_collections:
            self._ensure_collections(env)

        self._print_command(cmd)
        subprocess.run(cmd, check=True, cwd=self.ansible_root, env=env)

    @staticmethod
    def _ansible_env() -> dict[str, str]:
        env = os.environ.copy()
        env["ANSIBLE_CONFIG"] = str(ansible_config_path())
        executable_dir = str(Path(sys.executable).parent)
        env["PATH"] = os.pathsep.join([executable_dir, env.get("PATH", "")])
        return env

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

    def _ensure_collections(self, env: dict[str, str]) -> None:
        if not self._missing_collections():
            return

        requirements = self._collections_requirements_path()
        cmd = [
            "ansible-galaxy",
            "collection",
            "install",
            "--timeout",
            str(GALAXY_SERVER_TIMEOUT_SECONDS),
            "--upgrade",
            "-r",
            self._relative(requirements),
            "-p",
            self._relative(self._collections_path()),
        ]
        self._print_command(cmd)
        try:
            subprocess.run(
                cmd,
                check=True,
                cwd=self.ansible_root,
                env=env,
                timeout=GALAXY_INSTALL_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "Timed out installing Ansible collections from "
                f"{self._relative(requirements)}"
            ) from exc

    @staticmethod
    def _print_command(cmd: list[str]) -> None:
        print(f"Running: {shlex.join(cmd)}", file=sys.stderr, flush=True)

    def _missing_collections(self) -> list[str]:
        return [
            requirement.name
            for requirement in self._required_collections()
            if not self._collection_satisfies(requirement)
        ]

    def _required_collections(self) -> list[CollectionRequirement]:
        requirements = self._collections_requirements_path()
        if not requirements.is_file():
            return []

        data = yaml.safe_load(requirements.read_text(encoding="utf-8")) or {}
        collections = data.get("collections") if isinstance(data, dict) else None
        if not isinstance(collections, list):
            return []

        required = []
        for collection in collections:
            if isinstance(collection, str):
                name = collection
                version = None
            elif isinstance(collection, dict):
                name = collection.get("name")
                version = collection.get("version")
            else:
                continue

            if isinstance(name, str) and name.strip():
                required.append(
                    CollectionRequirement(
                        name=name.strip(),
                        version=version.strip()
                        if isinstance(version, str) and version.strip()
                        else None,
                    )
                )

        return required

    def _collection_satisfies(self, requirement: CollectionRequirement) -> bool:
        collection_path = self._collection_install_path(requirement.name)
        if not collection_path.is_dir():
            return False
        if not requirement.version:
            return True

        installed_version = self._installed_collection_version(collection_path)
        if not installed_version:
            return False

        return self._version_satisfies(installed_version, requirement.version)

    def _collection_install_path(self, name: str) -> Path:
        parts = name.split(".", maxsplit=1)
        if len(parts) != 2:
            return self._collections_path() / "ansible_collections" / name

        namespace, collection = parts
        return (
            self._collections_path()
            / "ansible_collections"
            / namespace
            / collection
        )

    @staticmethod
    def _installed_collection_version(collection_path: Path) -> str | None:
        manifest = collection_path / "MANIFEST.json"
        if not manifest.is_file():
            return None

        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        collection_info = data.get("collection_info")
        if not isinstance(collection_info, dict):
            return None

        version = collection_info.get("version")
        return version if isinstance(version, str) else None

    @classmethod
    def _version_satisfies(cls, installed: str, requirement: str) -> bool:
        clauses = [clause.strip() for clause in requirement.split(",") if clause.strip()]
        return all(cls._version_clause_satisfies(installed, clause) for clause in clauses)

    @classmethod
    def _version_clause_satisfies(cls, installed: str, clause: str) -> bool:
        match = re.fullmatch(r"(<=|>=|==|!=|<|>|=)?\s*([0-9][0-9A-Za-z.+-]*)", clause)
        if not match:
            return False

        operator = match.group(1) or "=="
        required = match.group(2)
        installed_parts = cls._version_parts(installed)
        required_parts = cls._version_parts(required)
        if installed_parts is None or required_parts is None:
            return False

        if operator in ("=", "=="):
            return installed_parts == required_parts
        if operator == "!=":
            return installed_parts != required_parts
        if operator == ">=":
            return installed_parts >= required_parts
        if operator == ">":
            return installed_parts > required_parts
        if operator == "<=":
            return installed_parts <= required_parts
        if operator == "<":
            return installed_parts < required_parts
        return False

    @staticmethod
    def _version_parts(value: str) -> tuple[int, ...] | None:
        parts = []
        for part in value.split("."):
            match = re.match(r"\d+", part)
            if not match:
                return None
            parts.append(int(match.group(0)))

        while len(parts) < 3:
            parts.append(0)

        return tuple(parts)

    def _collections_path(self) -> Path:
        return self.ansible_root / "collections"

    def _collections_requirements_path(self) -> Path:
        return self._collections_path() / "requirements.yml"
