from pathlib import Path


DEFAULT_SITE = "kanagawa01"
DEFAULT_PLAYBOOK = "site"
PUBLIC_PLAYBOOKS = ("site", "bootstrap")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def ansible_root() -> Path:
    return repo_root() / "ansible"


def ansible_config_path() -> Path:
    return ansible_root() / "ansible.cfg"


def inventory_path(site: str) -> Path:
    path = ansible_root() / "inventories" / site / "hosts.yml"
    if not path.is_file():
        raise RuntimeError(f"Unknown site '{site}': inventory not found at {path}")
    return path


def playbook_path(playbook: str) -> Path:
    requested = playbook.strip()
    playbook_dir = ansible_root() / "playbooks"
    path = playbook_dir / f"{requested}.yml"
    if path.is_file():
        return path

    raise RuntimeError(f"Unknown playbook '{playbook}': no playbook matched")


def sites() -> list[str]:
    inventories = ansible_root() / "inventories"
    if not inventories.is_dir():
        return []
    return sorted(
        path.name
        for path in inventories.iterdir()
        if (path / "hosts.yml").is_file()
    )


def public_playbooks() -> list[str]:
    playbook_dir = ansible_root() / "playbooks"
    if not playbook_dir.is_dir():
        return []
    return [name for name in PUBLIC_PLAYBOOKS if (playbook_dir / f"{name}.yml").is_file()]


def playbooks() -> list[str]:
    return public_playbooks()
