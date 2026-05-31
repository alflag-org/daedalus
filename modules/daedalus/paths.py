from pathlib import Path


DEFAULT_SITE = "kanagawa01"
DEFAULT_PLAYBOOK = "site"


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
    path = ansible_root() / "playbooks" / f"{playbook}.yml"
    if not path.is_file():
        raise RuntimeError(f"Unknown playbook '{playbook}': playbook not found at {path}")
    return path


def sites() -> list[str]:
    inventories = ansible_root() / "inventories"
    if not inventories.is_dir():
        return []
    return sorted(
        path.name
        for path in inventories.iterdir()
        if (path / "hosts.yml").is_file()
    )


def playbooks() -> list[str]:
    playbook_dir = ansible_root() / "playbooks"
    if not playbook_dir.is_dir():
        return []
    return sorted(path.stem for path in playbook_dir.glob("*.yml"))
