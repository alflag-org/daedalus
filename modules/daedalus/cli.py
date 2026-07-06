import subprocess
from collections.abc import Callable

import fire

from .ansible import AnsibleRunner
from .paths import DEFAULT_PLAYBOOK, DEFAULT_SITE, public_playbooks, sites


class Infra:
    def sites(self) -> None:
        self._print_lines(sites())

    def playbooks(self) -> None:
        self._print_lines(public_playbooks())

    def inventory(self, site: str = DEFAULT_SITE) -> None:
        self._run(lambda: AnsibleRunner(site=site).inventory_graph())

    def ping(self, site: str = DEFAULT_SITE, limit: str | None = None) -> None:
        self._run(lambda: AnsibleRunner(site=site).adhoc(module="ping", limit=limit))

    def check(
        self,
        site: str = DEFAULT_SITE,
        playbook: str = DEFAULT_PLAYBOOK,
        limit: str | None = None,
        tags: str | None = None,
        skip_tags: str | None = None,
        extra_vars: str | None = None,
    ) -> None:
        self._playbook(
            site=site,
            playbook=playbook,
            limit=limit,
            tags=tags,
            skip_tags=skip_tags,
            extra_vars=extra_vars,
            check=True,
            diff=False,
        )

    def diff(
        self,
        site: str = DEFAULT_SITE,
        playbook: str = DEFAULT_PLAYBOOK,
        limit: str | None = None,
        tags: str | None = None,
        skip_tags: str | None = None,
        extra_vars: str | None = None,
    ) -> None:
        self._playbook(
            site=site,
            playbook=playbook,
            limit=limit,
            tags=tags,
            skip_tags=skip_tags,
            extra_vars=extra_vars,
            check=True,
            diff=True,
        )

    def apply(
        self,
        site: str = DEFAULT_SITE,
        playbook: str = DEFAULT_PLAYBOOK,
        limit: str | None = None,
        tags: str | None = None,
        skip_tags: str | None = None,
        extra_vars: str | None = None,
        yes: bool = False,
    ) -> None:
        if not yes:
            raise SystemExit("Error: apply requires --yes")

        self._playbook(
            site=site,
            playbook=playbook,
            limit=limit,
            tags=tags,
            skip_tags=skip_tags,
            extra_vars=extra_vars,
            check=False,
            diff=False,
        )

    def _playbook(
        self,
        *,
        site: str,
        playbook: str,
        limit: str | None,
        tags: str | None,
        skip_tags: str | None,
        extra_vars: str | None,
        check: bool,
        diff: bool,
    ) -> None:
        self._run(
            lambda: AnsibleRunner(site=site).playbook(
                playbook=playbook,
                limit=limit,
                tags=tags,
                skip_tags=skip_tags,
                extra_vars=extra_vars,
                check=check,
                diff=diff,
            )
        )

    @staticmethod
    def _print_lines(values: list[str]) -> None:
        for value in values:
            print(value)

    @staticmethod
    def _run(action: Callable[[], None]) -> None:
        try:
            action()
        except RuntimeError as exc:
            raise SystemExit(f"Error: {exc}") from None
        except FileNotFoundError as exc:
            command = exc.filename or "required command"
            raise SystemExit(f"Error: {command} was not found in PATH") from None
        except subprocess.CalledProcessError as exc:
            raise SystemExit(f"Error: command failed with exit code {exc.returncode}") from None


def main() -> None:
    fire.Fire(Infra)
