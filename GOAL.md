
# Goal

Migrate KANAGAWA01 monitoring from Zabbix to Prometheus/Grafana.

Zabbix was being rebuilt from scratch, so remove it instead of preserving it.
This change must include explicit removal of Zabbix Agent from Daedalus.

Work on branch:

`codex/prometheus-monitoring-migration`

## Required outcome

- No active Daedalus converge path references `zabbix_agent`.
- No active Daedalus converge path references `services/zabbix`.
- `kng01-mgmt-zabbix-01` is replaced by `kng01-mgmt-monitor-01`.
- `svc_zabbix` is replaced by `svc_monitoring`.
- Zabbix Agent is removed and replaced with `node_exporter`.
- Prometheus/Grafana/Alertmanager/blackbox_exporter are installed on `kng01-mgmt-monitor-01`.
- Prometheus uses file-based service discovery under `/var/lib/prometheus/file_sd`.
- Hermes will own generated target files. Daedalus only prepares Prometheus to read them.
- Zabbix API registration must not be implemented.
- Zabbix server/frontend/MySQL implementation must be removed from active monitoring.

## Commit split

Use these commits:

1. `refactor(inventory): replace zabbix host with monitor host`
2. `refactor(monitoring): remove zabbix agent converge`
3. `feat(monitoring): add node exporter role`
4. `feat(monitoring): add prometheus stack roles`
5. `docs(monitoring): document prometheus architecture`
6. `test(monitoring): replace zabbix regression coverage`

## Inventory changes

Update `ansible/inventories/kanagawa01/hosts.yml`.

Replace:

```yaml
kng01-mgmt-zabbix-01:
  ansible_host: 10.10.10.250
````

with:

```yaml
kng01-mgmt-monitor-01:
  ansible_host: 10.10.10.250
```

Remove:

```yaml
kng01-mgmt-mysql-shared-01:
  ansible_host: 10.10.10.221
```

Remove groups:

```yaml
svc_zabbix:
svc_mysql:
```

Add:

```yaml
svc_monitoring:
  hosts:
    kng01-mgmt-monitor-01: {}
```

Ensure `kng01-mgmt-monitor-01` is in:

```yaml
kng01_mgmt
provider_proxmox
platform_vm
svc_monitoring
```

Do not keep `kng01-mgmt-zabbix-01` anywhere.

## Host vars

Delete:

```text
ansible/inventories/kanagawa01/host_vars/kng01-mgmt-zabbix-01.yml
ansible/inventories/kanagawa01/host_vars/kng01-mgmt-mysql-shared-01.yml
```

Create:

```text
ansible/inventories/kanagawa01/host_vars/kng01-mgmt-monitor-01.yml
```

Content:

```yaml
---
hostname: kng01-mgmt-monitor-01
site: kng01
zone: mgmt
role: monitor
virtualization_type: vm
os_distribution: Ubuntu
os_version: "26.04"

network_address: 10.10.10.250/24
network_ipv4_address: 10.10.10.250
network_prefix_length: 24
network_gateway: 10.10.10.1
network_dns_resolvers:
  - 10.10.10.240
  - 10.10.10.241
network_primary_fqdn: kng01-mgmt-monitor-01.srv.alflag.internal
network_service_aliases:
  - monitor.srv.alflag.internal
  - prometheus.srv.alflag.internal
  - grafana.srv.alflag.internal
  - alertmanager.srv.alflag.internal

systemd_resolved_dns:
  - 10.10.10.240
  - 10.10.10.241
systemd_resolved_domains:
  - srv.alflag.internal

ssh_server_enabled: true
systemd_resolved_enabled: true

node_exporter_enabled: true

monitoring_stack_enabled: true
prometheus_enabled: true
alertmanager_enabled: true
grafana_enabled: true
blackbox_exporter_enabled: true
```

Remove `zabbix_agent_enabled` from all host_vars.

Add global monitoring defaults to `ansible/inventories/kanagawa01/group_vars/kanagawa01.yml`:

```yaml
monitoring_enabled: true
node_exporter_enabled: true
node_exporter_listen_address: 0.0.0.0
node_exporter_listen_port: 9100
```

## Foundation playbook

Update `ansible/playbooks/components/foundation.yml`.

Remove:

```yaml
- role: zabbix_agent
  when: zabbix_agent_enabled | default(false)
```

Add:

```yaml
- role: node_exporter
  when: node_exporter_enabled | default(false)
```

## Services playbook

Update `ansible/playbooks/components/services.yml`.

Remove imports:

```yaml
services/mysql.yml
services/zabbix.yml
```

Add:

```yaml
- name: Converge monitoring services
  ansible.builtin.import_playbook: services/monitoring.yml
```

Create `ansible/playbooks/components/services/monitoring.yml`:

```yaml
---
- name: Converge monitoring service hosts
  hosts: svc_monitoring
  gather_facts: true

  roles:
    - role: services/monitoring  # noqa role-name[path]
      when: monitoring_stack_enabled | default(false)
```

## Remove Zabbix roles

Delete:

```text
ansible/roles/zabbix_agent/
ansible/roles/services/zabbix/
ansible/roles/components/zabbix_server/
```

Also remove these vars files:

```text
ansible/inventories/kanagawa01/group_vars/svc_zabbix.yml
```

Do not leave active role references to Zabbix.

## Add node_exporter role

Create:

```text
ansible/roles/node_exporter/defaults/main.yml
ansible/roles/node_exporter/tasks/main.yml
ansible/roles/node_exporter/handlers/main.yml
ansible/roles/node_exporter/templates/prometheus-node-exporter.j2
```

`defaults/main.yml`:

```yaml
---
node_exporter_enabled: false
node_exporter_package: prometheus-node-exporter
node_exporter_service_name: prometheus-node-exporter
node_exporter_config_path: /etc/default/prometheus-node-exporter
node_exporter_listen_address: 0.0.0.0
node_exporter_listen_port: 9100
node_exporter_extra_args: []
```

`templates/prometheus-node-exporter.j2`:

```jinja
# Managed by Daedalus.
ARGS="--web.listen-address={{ node_exporter_listen_address }}:{{ node_exporter_listen_port }}{% for arg in node_exporter_extra_args %} {{ arg }}{% endfor %}"
```

`handlers/main.yml`:

```yaml
---
- name: Restart node exporter
  ansible.builtin.service:
    name: "{{ node_exporter_service_name }}"
    state: restarted
  when: not ansible_check_mode
```

`tasks/main.yml`:

```yaml
---
- name: Install node exporter
  ansible.builtin.apt:
    name: "{{ node_exporter_package }}"
    state: present
    update_cache: true
  when:
    - node_exporter_enabled | bool
    - not ansible_check_mode

- name: Render node exporter defaults
  ansible.builtin.template:
    src: prometheus-node-exporter.j2
    dest: "{{ node_exporter_config_path }}"
    owner: root
    group: root
    mode: "0644"
  notify: Restart node exporter
  when: node_exporter_enabled | bool

- name: Enable and start node exporter
  ansible.builtin.service:
    name: "{{ node_exporter_service_name }}"
    state: started
    enabled: true
  when:
    - node_exporter_enabled | bool
    - not ansible_check_mode

- name: Validate node exporter port
  ansible.builtin.wait_for:
    host: 127.0.0.1
    port: "{{ node_exporter_listen_port }}"
    timeout: 5
    state: started
  when:
    - node_exporter_enabled | bool
    - not ansible_check_mode
```

## Add monitoring service composition role

Create:

```text
ansible/roles/services/monitoring/tasks/main.yml
```

Content:

```yaml
---
- name: Apply Prometheus
  ansible.builtin.include_role:
    name: components/prometheus
  when: prometheus_enabled | default(false)

- name: Apply Alertmanager
  ansible.builtin.include_role:
    name: components/alertmanager
  when: alertmanager_enabled | default(false)

- name: Apply Grafana
  ansible.builtin.include_role:
    name: components/grafana
  when: grafana_enabled | default(false)

- name: Apply blackbox exporter
  ansible.builtin.include_role:
    name: components/blackbox_exporter
  when: blackbox_exporter_enabled | default(false)
```

## Add Prometheus role

Create:

```text
ansible/roles/components/prometheus/defaults/main.yml
ansible/roles/components/prometheus/tasks/main.yml
ansible/roles/components/prometheus/handlers/main.yml
ansible/roles/components/prometheus/templates/prometheus.yml.j2
ansible/roles/components/prometheus/templates/alerts.yml.j2
```

Defaults:

```yaml
---
prometheus_enabled: false
prometheus_package: prometheus
prometheus_service_name: prometheus
prometheus_config_dir: /etc/prometheus
prometheus_config_path: /etc/prometheus/prometheus.yml
prometheus_rules_dir: /etc/prometheus/rules
prometheus_file_sd_dir: /var/lib/prometheus/file_sd
prometheus_scrape_interval: 30s
prometheus_evaluation_interval: 30s
prometheus_listen_address: 127.0.0.1
prometheus_port: 9090
alertmanager_url: http://127.0.0.1:9093
```

`prometheus.yml.j2`:

```jinja
# Managed by Daedalus.
global:
  scrape_interval: {{ prometheus_scrape_interval }}
  evaluation_interval: {{ prometheus_evaluation_interval }}

alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - "127.0.0.1:9093"

rule_files:
  - "{{ prometheus_rules_dir }}/*.yml"

scrape_configs:
  - job_name: prometheus
    static_configs:
      - targets:
          - "127.0.0.1:{{ prometheus_port }}"
        labels:
          site: "{{ site_short_name | default('kng01') }}"
          zone: mgmt
          role: monitor
          managed_by: daedalus

  - job_name: node
    file_sd_configs:
      - files:
          - "{{ prometheus_file_sd_dir }}/node*.json"

  - job_name: blackbox_http
    metrics_path: /probe
    params:
      module:
        - http_2xx
    file_sd_configs:
      - files:
          - "{{ prometheus_file_sd_dir }}/blackbox_http*.json"
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - source_labels: [__param_target]
        target_label: instance
      - target_label: __address__
        replacement: 127.0.0.1:9115
```

`alerts.yml.j2`:

```jinja
# Managed by Daedalus.
groups:
  - name: kanagawa01-base
    rules:
      - alert: HostDown
        expr: up{job="node"} == 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Host is down"
          description: "{{ '{{' }} $labels.host | default($labels.instance) {{ '}}' }} is not responding to Prometheus scrape."

      - alert: BlackboxEndpointDown
        expr: probe_success{job="blackbox_http"} == 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "HTTP endpoint is down"
          description: "{{ '{{' }} $labels.instance {{ '}}' }} did not pass blackbox probe."

      - alert: LowDiskSpace
        expr: node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay"} < 0.10
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Low disk space"
          description: "{{ '{{' }} $labels.instance {{ '}}' }} has less than 10% disk space available."
```

`tasks/main.yml`:

```yaml
---
- name: Install Prometheus
  ansible.builtin.apt:
    name: "{{ prometheus_package }}"
    state: present
    update_cache: true
  when:
    - prometheus_enabled | bool
    - not ansible_check_mode

- name: Ensure Prometheus directories exist
  ansible.builtin.file:
    path: "{{ item }}"
    state: directory
    owner: prometheus
    group: prometheus
    mode: "0755"
  loop:
    - "{{ prometheus_config_dir }}"
    - "{{ prometheus_rules_dir }}"
    - "{{ prometheus_file_sd_dir }}"
  when:
    - prometheus_enabled | bool
    - not ansible_check_mode

- name: Render Prometheus configuration
  ansible.builtin.template:
    src: prometheus.yml.j2
    dest: "{{ prometheus_config_path }}"
    owner: prometheus
    group: prometheus
    mode: "0644"
  notify: Restart Prometheus
  when: prometheus_enabled | bool

- name: Render Prometheus alert rules
  ansible.builtin.template:
    src: alerts.yml.j2
    dest: "{{ prometheus_rules_dir }}/kanagawa01.yml"
    owner: prometheus
    group: prometheus
    mode: "0644"
  notify: Restart Prometheus
  when: prometheus_enabled | bool

- name: Enable and start Prometheus
  ansible.builtin.service:
    name: "{{ prometheus_service_name }}"
    state: started
    enabled: true
  when:
    - prometheus_enabled | bool
    - not ansible_check_mode

- name: Validate Prometheus port
  ansible.builtin.wait_for:
    host: 127.0.0.1
    port: "{{ prometheus_port }}"
    timeout: 10
    state: started
  when:
    - prometheus_enabled | bool
    - not ansible_check_mode
```

`handlers/main.yml`:

```yaml
---
- name: Restart Prometheus
  ansible.builtin.service:
    name: "{{ prometheus_service_name }}"
    state: restarted
  when: not ansible_check_mode
```

## Add Alertmanager role

Create `components/alertmanager` with package `prometheus-alertmanager`.

Config path:

```yaml
/etc/prometheus/alertmanager.yml
```

Initial config:

```yaml
# Managed by Daedalus.
route:
  receiver: default
  group_by:
    - alertname
    - site
    - zone
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h

receivers:
  - name: default
```

Do not configure real notification receivers yet.

## Add blackbox exporter role

Create `components/blackbox_exporter` with package `prometheus-blackbox-exporter`.

Config path:

```yaml
/etc/prometheus/blackbox.yml
```

Initial modules:

```yaml
# Managed by Daedalus.
modules:
  http_2xx:
    prober: http
    timeout: 5s
    http:
      valid_http_versions:
        - HTTP/1.1
        - HTTP/2.0
      follow_redirects: true
      preferred_ip_protocol: ip4

  tcp_connect:
    prober: tcp
    timeout: 5s
```

## Add Grafana role

Create `components/grafana`.

Use Grafana apt repository and install `grafana`.

Install packages:

```yaml
ca-certificates
python3-debian
grafana
```

Configure:

```text
/etc/grafana/provisioning/datasources/prometheus.yml
/etc/grafana/provisioning/dashboards/daedalus.yml
/var/lib/grafana/dashboards/kanagawa01-overview.json
```

Datasource provisioning:

```yaml
# Managed by Daedalus.
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://127.0.0.1:9090
    isDefault: true
```

Dashboard provider:

```yaml
# Managed by Daedalus.
apiVersion: 1
providers:
  - name: Daedalus
    orgId: 1
    folder: Daedalus
    type: file
    disableDeletion: false
    updateIntervalSeconds: 60
    options:
      path: /var/lib/grafana/dashboards
```

Keep dashboard minimal but valid JSON.

## Docs

Add:

```text
docs/monitoring.md
```

Document:

* Zabbix has been removed.
* Zabbix Agent is not installed by Daedalus.
* Prometheus/Grafana/Alertmanager/blackbox exporter run on `kng01-mgmt-monitor-01`.
* `node_exporter` is installed on monitored hosts.
* Prometheus reads `/var/lib/prometheus/file_sd/*.json`.
* Hermes owns generation of file_sd target files.
* Initial boundary is MGMT-to-MGMT and MGMT-to-DMZ pull.
* DMZ-to-MGMT metrics push is not used.
* Grafana/Prometheus must not be directly exposed to Internet.
* Cloudflare Access or MGMT-only access should be used for Grafana UI.

Update existing docs:

```text
README.md
docs/layout.md
docs/components.md
docs/operations.md
docs/migration.md
```

Remove or rewrite Zabbix references.

## Tests

Delete Zabbix-specific tests:

```text
tests/test_zabbix_mysql_roles.py
tests/test_zabbix_php_role.py
```

Update `tests/test_foundation_dns_boundaries.py`:

* Remove assertions expecting `zabbix_agent`.
* Remove expectations for `kng01-mgmt-zabbix-01`.
* Add expectation that `kng01-mgmt-monitor-01` is in `svc_monitoring`.
* Add expectation that `kng01-mgmt-monitor-01` uses `10.10.10.250`.
* Add expectation that `foundation.yml` applies `node_exporter` exactly once.
* Add expectation that active playbooks/roles do not reference `zabbix_agent`, `services/zabbix`, or `components/zabbix_server`.

Add `tests/test_monitoring_stack.py`:

Test:

* `services.yml` imports `services/monitoring.yml`.
* `services/monitoring.yml` targets `svc_monitoring`.
* `services/monitoring` includes Prometheus, Alertmanager, Grafana, and blackbox exporter components.
* Prometheus template contains `file_sd_configs`.
* Prometheus template reads `node*.json` and `blackbox_http*.json`.
* Alert rules include `HostDown` and `BlackboxEndpointDown`.
* No active inventory group named `svc_zabbix`.
* No active host named `kng01-mgmt-zabbix-01`.

## Validation

Run:

```bash
python -m pytest -q

cd ansible
ansible-playbook --syntax-check playbooks/site.yml
ansible-playbook --syntax-check playbooks/bootstrap.yml
ansible-playbook --syntax-check playbooks/cloudflare.yml
```

Then from control node:

```bash
atlas run infra check --site kanagawa01 --limit svc_monitoring
atlas run infra check --site kanagawa01 --limit kng01-dmz-web-01
```

## Non-goals

Do not implement Hermes in this Daedalus PR.

Hermes must be implemented separately to generate:

```text
/var/lib/prometheus/file_sd/node.json
/var/lib/prometheus/file_sd/blackbox_http.json
```

Do not reintroduce Zabbix registration.
Do not keep Zabbix Agent.
Do not keep Zabbix server/frontend as a dormant service.
