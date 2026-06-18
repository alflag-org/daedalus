# DNS Management

Daedalus manages DNS server host-side state for KANAGAWA01. It does not manage
authoritative zone record contents yet.

## Hosts

Recursive DNS:

- `kng01-mgmt-recdns-01` at `10.10.10.240`
- `kng01-mgmt-recdns-02` at `10.10.10.241`

Authoritative DNS:

- `kng01-mgmt-authdns-01` at `10.10.10.242`
- `kng01-mgmt-authdns-02` at `10.10.10.243`

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

The current zone metadata is:

```yaml
dns_authoritative_zones:
  - name: alflag.internal
    file: /etc/nsd/zones/alflag.internal.zone
```

Daedalus will not overwrite that file unless a zone entry explicitly provides a
`text` value. The normal path is to place or update the zone file manually on
both authoritative DNS hosts, then run validation.

## Add Zone Metadata

Add metadata under `ansible/inventories/kanagawa01/group_vars/svc_dns_authoritative.yml`:

```yaml
dns_authoritative_zones:
  - name: alflag.internal
    file: /etc/nsd/zones/alflag.internal.zone
  - name: example.alflag.internal
    file: /etc/nsd/zones/example.alflag.internal.zone
```

Then place the corresponding zone file manually on each authoritative DNS host.

## Validation

From the control node:

```bash
atlas run infra check --site kanagawa01 --limit svc_dns_recursive
atlas run infra check --site kanagawa01 --limit svc_dns_authoritative
```

On a recursive DNS host:

```bash
unbound-checkconf
dig +short . NS @127.0.0.1
dig +short alflag.internal SOA @127.0.0.1
```

On an authoritative DNS host:

```bash
nsd-checkconf /etc/nsd/nsd.conf
nsd-checkzone alflag.internal /etc/nsd/zones/alflag.internal.zone
```

If an authoritative zone file is missing, Daedalus should fail with a clear
message instead of committing placeholder records or secrets to this repository.
