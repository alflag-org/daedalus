#!/bin/bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"

if [[ -n "${ANSIBLE_VAULT_PASSWORD:-}" ]]; then
  printf "%s" "${ANSIBLE_VAULT_PASSWORD}"
  exit 0
fi

if [[ -f "${repo_root}/secrets/ansible_vault.env" ]]; then
  # shellcheck disable=SC1091
  source "${repo_root}/secrets/ansible_vault.env"
fi

if [[ -z "${ANSIBLE_VAULT_PASSWORD:-}" ]]; then
  echo "ANSIBLE_VAULT_PASSWORD is not set" >&2
  exit 1
fi

printf "%s" "${ANSIBLE_VAULT_PASSWORD}"
