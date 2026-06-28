# DNS Management

Daedalus manages DNS server host-side state. It does not manage
authoritative zone record contents yet.

## Hosts

Recursive and authoritative DNS host membership lives in inventory. Use
`svc_dns_recursive` and `svc_dns_authoritative` group membership when current
host state is needed. Address, listener, and resolver values belong in
host/group vars, not in docs.

## Managed State

Daedalus manages:

- Unbound package, config, service, listen addresses, access-control, and
  internal stub-zone or forward-zone metadata
- NSD package, config, service, listen addresses, and zone registration metadata
- NSD zone file existence validation when zone text is not supplied
- basic validation commands such as `unbound-checkconf`, `nsd-checkconf`,
  `nsd-checkzone`, and local `dig` checks

Recursive DNS stubs `alflag.internal` to the authoritative DNS hosts.

## Manual State

Authoritative zone record contents remain manual for now:

- SOA, NS, A, CNAME, and other record contents
- serial update workflow
- DNSSEC signing
- external DNS and Cloudflare DNS

Zone metadata uses this shape:

```yaml
dns_authoritative_zones:
  - name: <zone-name>
    file: <absolute-zone-file-path>
```

Daedalus will not overwrite that file unless a zone entry explicitly provides a
`text` value. The normal path is to place or update the zone file manually on
both authoritative DNS hosts, then run validation.

## Add Zone Metadata

Add metadata under `ansible/inventories/default/group_vars/svc_dns_authoritative.yml`.
Use real values in inventory, not copied examples in docs:

```yaml
dns_authoritative_zones:
  - name: <zone-name>
    file: <absolute-zone-file-path>
```

Then place the corresponding zone file manually on each authoritative DNS host.

## Validation

From the control node:

```bash
atlas run infra check --site default --limit svc_dns_recursive
atlas run infra check --site default --limit svc_dns_authoritative
```

On a recursive DNS host:

```bash
unbound-checkconf
dig +short <query-name> <query-type> @<recursive-listener>
```

On an authoritative DNS host:

```bash
nsd-checkconf /etc/nsd/nsd.conf
nsd-checkzone <zone-name> <absolute-zone-file-path>
```

If an authoritative zone file is missing, Daedalus should fail with a clear
message instead of committing placeholder records or secrets to this repository.
