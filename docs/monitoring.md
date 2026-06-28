# Monitoring

Monitoring uses Prometheus. Zabbix server, frontend, database wiring, and
Zabbix Agent are no longer installed by Daedalus.

During the migration, Daedalus also runs a temporary retired monitoring cleanup
role from the foundation converge. It stops old Zabbix services, purges Zabbix
packages, and removes leftover Zabbix configuration, repository, log, and data
paths from existing hosts.

The monitoring service host is `monitor01`. Daedalus installs
Prometheus, Grafana, Alertmanager, and blackbox exporter there through the
`svc_monitoring` inventory group.

`node_exporter` is installed on monitored hosts through the foundation converge.
Prometheus reads file-based service discovery entries from
`/var/lib/prometheus/file_sd/*.json`, including `node*.json` and
`blackbox_http*.json` target files. Hermes owns generation of those files;
Daedalus only prepares Prometheus to read them.

The initial metrics boundary is MGMT-to-MGMT and MGMT-to-DMZ pull scraping.
DMZ-to-MGMT metrics push is not used.

The shared MySQL service is retained as independent infrastructure. It is not a
Zabbix component and is not removed by this migration.

Grafana, Prometheus, and Alertmanager are internal services. Do not expose them
directly to the Internet. Use Cloudflare Access or MGMT-only access for the
Grafana UI.
