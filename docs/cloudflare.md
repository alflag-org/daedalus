# Cloudflare Host-Side Components

Daedalus manages only the host-side pieces needed for Cloudflare connectivity:

- `cloudflared` installation
- `/etc/cloudflared` ownership and token environment file rendering
- the local `cloudflared` systemd service
- conservative local SSH server policy for Cloudflare SSH targets
- local validation that SSH is reachable on the expected host and port

Daedalus does not manage Cloudflare dashboard or API resources yet.

## Tunnel Tokens

Do not commit tunnel tokens.

For apply runs, `cloudflared_enabled=true` requires:

```yaml
cloudflared_tunnel_token: "..."
```

The value can come from the operator secret store, the operator vars file
loaded by `infra`, or an operator-provided extra var. Daedalus renders:

```text
/etc/cloudflared/token.env
```

with mode `0600`. Check mode does not require the token so operators can review
planned host changes without committing or exposing secret material.

## cloudflared Service

The service executes the local tunnel in token mode:

```text
cloudflared tunnel --no-autoupdate run --token "$TUNNEL_TOKEN"
```

Metrics are disabled by default. Enable them with:

```yaml
cloudflared_metrics_enabled: true
cloudflared_metrics_address: <metrics-listen-address>
cloudflared_metrics_port: <metrics-listen-port>
```

## Cloudflare SSH Targets

`cloudflare_ssh_target` prepares a host so Cloudflare Access SSH or Tunnel can
reach a local SSH daemon. The role depends on the local `ssh_server` role and
validates `cloudflare_ssh_target_host:cloudflare_ssh_target_port` from the
managed host.

TCP forwarding defaults to `no`. Hosts that need client-side port forwarding,
such as VS Code Remote SSH, should set:

```yaml
ssh_server_allow_tcp_forwarding: local
```

Use `yes` only for hosts that deliberately need both local and remote TCP
forwarding.

It does not create:

- Access applications
- Access policies
- tunnel routes
- private hostnames
- DNS records

Those resources remain manual, dashboard-managed, or Terraform-managed future
work.

## Validation

Focused checks from the control node:

```bash
atlas run infra check --playbook cloudflare --limit connector01
atlas run infra check --playbook cloudflare --limit bastion01
```

After apply, validate local host-side state:

```bash
cloudflared version
systemctl is-active cloudflared
sshd -t
```

External reachability through Access or a private hostname must be validated
outside Daedalus until Cloudflare-side state is brought under Terraform or
another explicit management path.
