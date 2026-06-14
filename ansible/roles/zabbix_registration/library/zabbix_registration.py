#!/usr/bin/python

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from typing import Any

from ansible.module_utils.basic import AnsibleModule


DOCUMENTATION = r"""
---
module: zabbix_registration
short_description: Synchronize Daedalus inventory hosts into Zabbix
description:
  - Ensures Zabbix host groups exist.
  - Resolves templates by technical or visible name.
  - Creates missing hosts and updates existing hosts through the Zabbix API.
  - Supports check mode by reporting planned changes without mutation.
options:
  api_url:
    description: Full Zabbix JSON-RPC endpoint URL.
    required: true
    type: str
  api_token:
    description: Zabbix API token used as an Authorization bearer token.
    required: true
    type: str
  hosts:
    description: Inventory host projection built by the role.
    required: true
    type: list
    elements: dict
  default_templates:
    description: Templates linked to hosts unless the host overrides zabbix_templates.
    type: list
    elements: str
    default: []
  service_templates:
    description: Additional templates keyed by Ansible inventory group name.
    type: dict
    default: {}
  default_agent_interface:
    description: Default agent interface settings.
    type: dict
    default: {}
  validate_certs:
    description: Validate TLS certificates when api_url uses HTTPS.
    type: bool
    default: true
  timeout:
    description: HTTP request timeout in seconds.
    type: int
    default: 30
author:
  - Daedalus maintainers
"""

EXAMPLES = r"""
- name: Synchronize Zabbix host registration
  zabbix_registration:
    api_url: "{{ zabbix_api_url }}"
    api_token: "{{ zabbix_api_token }}"
    hosts: "{{ zabbix_registration_inventory_hosts }}"
    default_templates: "{{ zabbix_templates }}"
"""

RETURN = r"""
actions:
  description: Human-readable actions applied or planned.
  returned: always
  type: list
  elements: dict
managed_hosts:
  description: Desired managed host names processed by the module.
  returned: always
  type: list
  elements: str
"""


AGENT_INTERFACE_TYPE = 1
HOST_STATUS_ENABLED = "0"

SERVICE_ROLE_RULES = (
    ("svc_zabbix", "zabbix", "Monitoring"),
    ("svc_dns_recursive", "dns_recursive", "DNS/Recursive"),
    ("svc_dns_authoritative", "dns_authoritative", "DNS/Authoritative"),
    ("svc_connector", "connector", "Connectors"),
    ("svc_workbench", "workbench", "Workbench"),
    ("svc_bastion", "bastion", "Bastion"),
    ("svc_web", "web", "Web"),
    ("cap_control_node", "control", "Control"),
)


class ZabbixApiError(RuntimeError):
    pass


class ZabbixClient:
    def __init__(
        self,
        api_url: str,
        api_token: str,
        validate_certs: bool,
        timeout: int,
    ) -> None:
        self.api_url = api_url
        self.api_token = api_token
        self.timeout = timeout
        self.next_request_id = 1
        self.context = None
        if api_url.startswith("https://") and not validate_certs:
            self.context = ssl._create_unverified_context()

    def call(self, method: str, params: dict[str, Any]) -> Any:
        request_id = self.next_request_id
        self.next_request_id += 1
        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
                "id": request_id,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self.api_url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json-rpc",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout,
                context=self.context,
            ) as response:
                raw_response = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise ZabbixApiError(
                f"Zabbix API HTTP {exc.code} while calling {method}: {details}"
            ) from exc
        except urllib.error.URLError as exc:
            raise ZabbixApiError(
                f"Zabbix API request failed while calling {method}: {exc.reason}"
            ) from exc

        try:
            payload = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            raise ZabbixApiError(
                f"Zabbix API returned invalid JSON while calling {method}"
            ) from exc

        if "error" in payload:
            error = payload["error"]
            message = error.get("message", "unknown error")
            data = error.get("data")
            if data:
                message = f"{message}: {data}"
            raise ZabbixApiError(f"Zabbix API {method} failed: {message}")

        return payload.get("result")


def unique_strings(values: list[Any]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def bool_to_zabbix_int(value: Any) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, int):
        return 1 if value else 0
    if isinstance(value, str):
        return 0 if value.strip().lower() in ("0", "false", "no", "off") else 1
    return 1 if value else 0


def clean_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def clean_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def value_from(entry: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = entry.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def site_group_name(entry: dict[str, Any]) -> str:
    site = value_from(entry, "site_name", "site")
    if not site:
        site = value_from(entry, "site_short_name")
    if not site:
        site = "site"
    return str(site).upper()


def site_tag_value(entry: dict[str, Any]) -> str:
    site = value_from(entry, "site", "site_short_name", "site_name")
    return str(site or "unknown").lower()


def zone_value(entry: dict[str, Any]) -> str:
    zone = value_from(entry, "zone", "network_zone")
    group_names = set(clean_list(entry.get("group_names")))
    if not zone:
        if "kng01_mgmt" in group_names:
            zone = "mgmt"
        elif "kng01_dmz" in group_names:
            zone = "dmz"
        elif "kng01_client" in group_names:
            zone = "client"
    return str(zone or "unknown").lower()


def role_value(entry: dict[str, Any]) -> str:
    role = value_from(entry, "role")
    if role:
        return str(role).lower()

    group_names = set(clean_list(entry.get("group_names")))
    for group_name, role_name, _group_suffix in SERVICE_ROLE_RULES:
        if group_name in group_names:
            return role_name

    if "platform_vm" in group_names:
        return "vm"
    if "platform_lxc" in group_names:
        return "lxc"
    return "host"


def derive_host_groups(entry: dict[str, Any]) -> list[str]:
    explicit = entry.get("zabbix_host_groups")
    if isinstance(explicit, list):
        return unique_strings(explicit)

    site_group = site_group_name(entry)
    zone_group = f"{site_group}/{zone_value(entry).upper()}"
    groups = [site_group, zone_group]

    inventory_groups = set(clean_list(entry.get("group_names")))
    for group_name, _role_name, group_suffix in SERVICE_ROLE_RULES:
        if group_name in inventory_groups:
            groups.append(f"{site_group}/{group_suffix}")

    return unique_strings(groups)


def normalize_template_list(raw_templates: Any) -> list[str]:
    return unique_strings(clean_list(raw_templates))


def derive_templates(
    entry: dict[str, Any],
    default_templates: list[str],
    service_templates: dict[str, Any],
) -> list[str]:
    explicit = entry.get("zabbix_templates")
    templates = (
        normalize_template_list(explicit)
        if isinstance(explicit, list)
        else list(default_templates)
    )

    group_names = set(clean_list(entry.get("group_names")))
    for group_name in sorted(group_names):
        templates.extend(normalize_template_list(service_templates.get(group_name)))

    return unique_strings(templates)


def normalize_tags(raw_tags: Any) -> list[dict[str, str]]:
    tags = []
    for raw_tag in clean_list(raw_tags):
        if not isinstance(raw_tag, dict):
            continue
        tag = str(raw_tag.get("tag", "")).strip()
        if not tag:
            continue
        tags.append({"tag": tag, "value": str(raw_tag.get("value", "")).strip()})
    return tags


def derive_tags(entry: dict[str, Any], default_tags: list[dict[str, str]]) -> list[dict[str, str]]:
    explicit_tags = entry.get("zabbix_tags")
    tags = list(default_tags)
    if isinstance(explicit_tags, list):
        tags.extend(normalize_tags(explicit_tags))

    tags.extend(
        [
            {"tag": "managed_by", "value": "daedalus"},
            {"tag": "site", "value": site_tag_value(entry)},
            {"tag": "zone", "value": zone_value(entry)},
            {"tag": "role", "value": role_value(entry)},
        ]
    )

    primary_fqdn = value_from(entry, "network_primary_fqdn")
    if primary_fqdn:
        tags.append({"tag": "fqdn", "value": str(primary_fqdn)})

    for alias in clean_list(entry.get("network_service_aliases")):
        tags.append({"tag": "alias", "value": str(alias)})

    return unique_tags(tags)


def unique_tags(tags: list[dict[str, str]]) -> list[dict[str, str]]:
    seen = set()
    result = []
    for tag in tags:
        key = (tag["tag"], tag.get("value", ""))
        if key in seen:
            continue
        seen.add(key)
        result.append({"tag": tag["tag"], "value": tag.get("value", "")})
    return result


def network_ip_from_address(network_address: Any) -> str | None:
    if not network_address:
        return None
    return str(network_address).split("/", maxsplit=1)[0].strip() or None


def derive_interface(
    entry: dict[str, Any],
    default_agent_interface: dict[str, Any],
) -> dict[str, Any]:
    explicit = clean_dict(entry.get("zabbix_agent_interface"))
    merged = dict(default_agent_interface)
    merged.update(explicit)

    ip = value_from(merged, "ip")
    if not ip:
        ip = value_from(entry, "network_ipv4_address", "ansible_host")
    if not ip:
        ip = network_ip_from_address(entry.get("network_address"))

    dns = value_from(merged, "dns")
    if not dns:
        dns = value_from(entry, "network_primary_fqdn")
    if not dns:
        dns = ""

    useip = bool_to_zabbix_int(merged.get("useip", True))
    if not ip and useip == 1:
        raise ValueError(
            f"{entry.get('inventory_hostname', '<unknown>')} is missing an IP "
            "for its Zabbix agent interface"
        )

    if useip == 0 and not dns:
        dns = str(entry.get("inventory_hostname", ""))

    return {
        "type": AGENT_INTERFACE_TYPE,
        "main": 1,
        "useip": useip,
        "ip": str(ip or ""),
        "dns": str(dns),
        "port": str(merged.get("port", "10050")),
    }


def desired_host(
    entry: dict[str, Any],
    default_templates: list[str],
    service_templates: dict[str, Any],
    default_tags: list[dict[str, str]],
    default_agent_interface: dict[str, Any],
) -> dict[str, Any]:
    host = value_from(entry, "zabbix_hostname", "inventory_hostname")
    if not host:
        raise ValueError("managed host entry is missing inventory_hostname")
    host = str(host)
    name = str(value_from(entry, "zabbix_visible_name", "inventory_hostname") or host)

    return {
        "host": host,
        "name": name,
        "groups": derive_host_groups(entry),
        "templates": derive_templates(entry, default_templates, service_templates),
        "tags": derive_tags(entry, default_tags),
        "interface": derive_interface(entry, default_agent_interface),
    }


def get_host_groups(client: ZabbixClient, names: list[str]) -> dict[str, str]:
    if not names:
        return {}
    result = client.call(
        "hostgroup.get",
        {
            "output": ["groupid", "name"],
            "filter": {"name": names},
        },
    )
    return {group["name"]: group["groupid"] for group in result}


def create_host_group(client: ZabbixClient, name: str) -> str:
    result = client.call("hostgroup.create", {"name": name})
    groupids = result.get("groupids", [])
    if not groupids:
        raise ZabbixApiError(f"Zabbix did not return an ID for host group {name}")
    return str(groupids[0])


def resolve_templates(client: ZabbixClient, names: list[str]) -> dict[str, str]:
    if not names:
        return {}

    candidates: list[dict[str, Any]] = []
    for property_name in ("host", "name"):
        result = client.call(
            "template.get",
            {
                "output": ["templateid", "host", "name"],
                "filter": {property_name: names},
            },
        )
        candidates.extend(result)

    resolved: dict[str, str] = {}
    ambiguous = []
    wanted = set(names)
    for template in candidates:
        for key_name in ("host", "name"):
            key = template.get(key_name)
            if key not in wanted:
                continue
            templateid = str(template["templateid"])
            if key in resolved and resolved[key] != templateid:
                ambiguous.append(key)
            resolved[key] = templateid

    if ambiguous:
        raise ZabbixApiError(
            "Template name matched multiple templates: "
            + ", ".join(sorted(set(ambiguous)))
        )

    missing = sorted(wanted - set(resolved.keys()))
    if missing:
        raise ZabbixApiError(
            "Template(s) not found in Zabbix: " + ", ".join(missing)
        )

    return resolved


def get_hosts(client: ZabbixClient, names: list[str]) -> dict[str, dict[str, Any]]:
    if not names:
        return {}
    result = client.call(
        "host.get",
        {
            "output": ["hostid", "host", "name", "status"],
            "filter": {"host": names},
            "selectGroups": ["groupid", "name"],
            "selectInterfaces": [
                "interfaceid",
                "type",
                "main",
                "useip",
                "ip",
                "dns",
                "port",
            ],
            "selectParentTemplates": ["templateid", "host", "name"],
            "selectTags": "extend",
        },
    )
    return {host["host"]: host for host in result}


def template_objects(desired: dict[str, Any], template_ids: dict[str, str]) -> list[dict[str, str]]:
    return [{"templateid": template_ids[name]} for name in desired["templates"]]


def group_objects(desired: dict[str, Any], group_ids: dict[str, str]) -> list[dict[str, str]]:
    return [{"groupid": group_ids[name]} for name in desired["groups"]]


def create_payload(
    desired: dict[str, Any],
    group_ids: dict[str, str],
    template_ids: dict[str, str],
) -> dict[str, Any]:
    return {
        "host": desired["host"],
        "name": desired["name"],
        "status": 0,
        "groups": group_objects(desired, group_ids),
        "interfaces": [desired["interface"]],
        "templates": template_objects(desired, template_ids),
        "tags": desired["tags"],
    }


def find_main_agent_interface(host: dict[str, Any]) -> dict[str, Any] | None:
    agent_interfaces = [
        interface
        for interface in clean_list(host.get("interfaces"))
        if str(interface.get("type")) == str(AGENT_INTERFACE_TYPE)
    ]
    for interface in agent_interfaces:
        if str(interface.get("main")) == "1":
            return interface
    return agent_interfaces[0] if agent_interfaces else None


def update_interfaces_payload(
    current_host: dict[str, Any],
    desired_interface: dict[str, Any],
) -> list[dict[str, Any]]:
    existing = find_main_agent_interface(current_host)
    managed_interface = dict(desired_interface)
    if existing and existing.get("interfaceid"):
        managed_interface["interfaceid"] = existing["interfaceid"]

    interfaces = [managed_interface]
    existing_id = existing.get("interfaceid") if existing else None
    for interface in clean_list(current_host.get("interfaces")):
        if interface.get("interfaceid") == existing_id:
            continue
        if str(interface.get("type")) == str(AGENT_INTERFACE_TYPE):
            continue
        interfaces.append(
            {
                key: interface[key]
                for key in (
                    "interfaceid",
                    "type",
                    "main",
                    "useip",
                    "ip",
                    "dns",
                    "port",
                )
                if key in interface
            }
        )
    return interfaces


def update_payload(
    current_host: dict[str, Any],
    desired: dict[str, Any],
    group_ids: dict[str, str],
    template_ids: dict[str, str],
) -> dict[str, Any]:
    return {
        "hostid": current_host["hostid"],
        "host": desired["host"],
        "name": desired["name"],
        "status": 0,
        "groups": group_objects(desired, group_ids),
        "interfaces": update_interfaces_payload(current_host, desired["interface"]),
        "templates": template_objects(desired, template_ids),
        "tags": desired["tags"],
    }


def sorted_names(items: list[dict[str, Any]], name_key: str = "name") -> list[str]:
    return sorted(str(item.get(name_key, "")) for item in items if item.get(name_key))


def current_template_names(host: dict[str, Any]) -> list[str]:
    templates = clean_list(host.get("parentTemplates"))
    names = []
    for template in templates:
        names.append(str(template.get("host") or template.get("name") or ""))
    return sorted(name for name in names if name)


def normalized_interface(interface: dict[str, Any] | None) -> dict[str, str] | None:
    if not interface:
        return None
    return {
        "type": str(interface.get("type", "")),
        "main": str(interface.get("main", "")),
        "useip": str(interface.get("useip", "")),
        "ip": str(interface.get("ip", "")),
        "dns": str(interface.get("dns", "")),
        "port": str(interface.get("port", "")),
    }


def normalized_desired_interface(interface: dict[str, Any]) -> dict[str, str]:
    return {
        "type": str(interface["type"]),
        "main": str(interface["main"]),
        "useip": str(interface["useip"]),
        "ip": str(interface["ip"]),
        "dns": str(interface["dns"]),
        "port": str(interface["port"]),
    }


def normalized_tags(tags: list[dict[str, Any]]) -> list[tuple[str, str]]:
    normalized = [
        (str(tag.get("tag", "")), str(tag.get("value", "")))
        for tag in tags
        if tag.get("tag")
    ]
    return sorted(set(normalized))


def change_reasons(current_host: dict[str, Any], desired: dict[str, Any]) -> list[str]:
    reasons = []
    if str(current_host.get("name", "")) != desired["name"]:
        reasons.append("visible name")
    if str(current_host.get("status", "")) != HOST_STATUS_ENABLED:
        reasons.append("status")
    if sorted_names(clean_list(current_host.get("groups"))) != sorted(desired["groups"]):
        reasons.append("host groups")
    if current_template_names(current_host) != sorted(desired["templates"]):
        reasons.append("templates")
    if normalized_tags(clean_list(current_host.get("tags"))) != normalized_tags(
        desired["tags"]
    ):
        reasons.append("tags")
    if normalized_interface(find_main_agent_interface(current_host)) != (
        normalized_desired_interface(desired["interface"])
    ):
        reasons.append("agent interface")
    return reasons


def action(
    operation: str,
    host: str | None = None,
    name: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {"operation": operation}
    if host is not None:
        result["host"] = host
    if name is not None:
        result["name"] = name
    if details is not None:
        result["details"] = details
    return result


def run_module() -> None:
    module = AnsibleModule(
        argument_spec={
            "api_url": {"type": "str", "required": True},
            "api_token": {"type": "str", "required": True, "no_log": True},
            "hosts": {"type": "list", "elements": "dict", "required": True},
            "default_templates": {
                "type": "list",
                "elements": "str",
                "default": [],
            },
            "service_templates": {"type": "dict", "default": {}},
            "default_tags": {"type": "list", "elements": "dict", "default": []},
            "default_agent_interface": {"type": "dict", "default": {}},
            "validate_certs": {"type": "bool", "default": True},
            "timeout": {"type": "int", "default": 30},
        },
        supports_check_mode=True,
    )

    params = module.params
    client = ZabbixClient(
        params["api_url"],
        params["api_token"],
        params["validate_certs"],
        params["timeout"],
    )
    actions = []

    try:
        default_templates = unique_strings(params["default_templates"])
        default_tags = normalize_tags(params["default_tags"])
        desired_hosts = [
            desired_host(
                entry,
                default_templates,
                params["service_templates"],
                default_tags,
                params["default_agent_interface"],
            )
            for entry in params["hosts"]
            if bool_to_zabbix_int(entry.get("zabbix_managed", True)) == 1
        ]

        desired_group_names = unique_strings(
            group for host in desired_hosts for group in host["groups"]
        )
        desired_template_names = unique_strings(
            template for host in desired_hosts for template in host["templates"]
        )
        desired_host_names = unique_strings(host["host"] for host in desired_hosts)

        group_ids = get_host_groups(client, desired_group_names)
        missing_groups = [
            name for name in desired_group_names if name not in group_ids
        ]
        for group_name in missing_groups:
            actions.append(action("create_host_group", name=group_name))
            if not module.check_mode:
                group_ids[group_name] = create_host_group(client, group_name)

        template_ids = resolve_templates(client, desired_template_names)
        current_hosts = get_hosts(client, desired_host_names)

        for host in desired_hosts:
            current_host = current_hosts.get(host["host"])
            if not current_host:
                actions.append(
                    action(
                        "create_host",
                        host=host["host"],
                        details={
                            "groups": host["groups"],
                            "templates": host["templates"],
                            "interface": host["interface"],
                            "tags": host["tags"],
                        },
                    )
                )
                if not module.check_mode:
                    client.call("host.create", create_payload(host, group_ids, template_ids))
                continue

            reasons = change_reasons(current_host, host)
            if not reasons:
                continue

            actions.append(
                action(
                    "update_host",
                    host=host["host"],
                    details={"changes": reasons},
                )
            )
            if not module.check_mode:
                client.call(
                    "host.update",
                    update_payload(current_host, host, group_ids, template_ids),
                )

    except (ZabbixApiError, ValueError) as exc:
        module.fail_json(msg=str(exc), actions=actions)

    module.exit_json(
        changed=bool(actions),
        actions=actions,
        managed_hosts=desired_host_names,
    )


def main() -> None:
    run_module()


if __name__ == "__main__":
    main()
