#!/usr/bin/env bash
# Installs the executor VM tools. Idempotent. Run as root through Run Command.
# Versions follow the documented Terraform path (azd 1.37.1, Terraform 1.13.0).
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive HOME="${HOME:-/root}" NEEDRESTART_MODE=a
AZD_VERSION="1.37.1"
TERRAFORM_VERSION="1.13.0"

cloud-init status --wait >/dev/null 2>&1 || true
apt-get update -qq
apt-get install -y -qq ca-certificates curl git jq unzip python3 python3-venv python3-pip >/dev/null 2>&1
command -v az >/dev/null || curl -fsSL https://aka.ms/InstallAzureCLIDeb | bash >/dev/null 2>&1
if ! azd version 2>/dev/null | grep -q "$AZD_VERSION"; then
  curl -fsSL https://aka.ms/install-azd.sh | bash -s -- --version "$AZD_VERSION" >/dev/null
fi
if ! terraform version 2>/dev/null | grep -q "v$TERRAFORM_VERSION"; then
  curl -fsSLo /tmp/terraform.zip "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip"
  unzip -o -q /tmp/terraform.zip terraform -d /usr/local/bin
  rm -f /tmp/terraform.zip
fi
mkdir -p /var/lib/relval
chmod 700 /var/lib/relval
az version --query '"azure-cli"' -o tsv
azd version
terraform version | head -n1
python3 --version
