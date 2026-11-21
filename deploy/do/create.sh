#!/usr/bin/env bash
# Create droplet fb-web-1 + reserved IP + cloud firewall on DigitalOcean.
# Usage: DO_TOKEN_FILE=<path to token file> SSH_ALLOW_IP=1.2.3.4 ./create.sh
set -euo pipefail
cd "$(dirname "$0")"

TOKEN_FILE="${DO_TOKEN_FILE:?set DO_TOKEN_FILE}"
export DIGITALOCEAN_ACCESS_TOKEN="$(grep -oE 'dop_v1_[A-Za-z0-9]+' "$TOKEN_FILE" | head -1)"
NAME="${NAME:-fb-web-1}"
REGION="${REGION:-ams3}"
SIZE="${SIZE:-s-1vcpu-1gb}"
IMAGE="${IMAGE:-ubuntu-24-04-x64}"
KEY_FILE="${KEY_FILE:-$HOME/.ssh/id_ed25519_fbweb.pub}"
SSH_ALLOW_IP="${SSH_ALLOW_IP:?set SSH_ALLOW_IP}"

FP=$(ssh-keygen -E md5 -lf "$KEY_FILE" | awk '{print $2}' | sed 's/^MD5://')
if ! doctl compute ssh-key get "$FP" >/dev/null 2>&1; then
  doctl compute ssh-key import fb-web-deploy --public-key-file "$KEY_FILE" >/dev/null
fi

PUB=$(cat "$KEY_FILE")
sed "s|__DEPLOY_PUBKEY__|$PUB|" cloud-init.yaml > /tmp/fbweb-cloud-init.yaml

if ! doctl compute droplet list --format Name --no-header | grep -qx "$NAME"; then
  doctl compute droplet create "$NAME" --region "$REGION" --size "$SIZE" --image "$IMAGE" \
    --ssh-keys "$FP" --user-data-file /tmp/fbweb-cloud-init.yaml \
    --enable-monitoring --tag-name fb-web --wait --format ID,Name,PublicIPv4 --no-header
fi
ID=$(doctl compute droplet list --format ID,Name --no-header | awk -v n="$NAME" '$2==n{print $1}')

RIP=$(doctl compute reserved-ip list --format IP,DropletID --no-header | awk -v id="$ID" '$2==id{print $1}')
if [ -z "$RIP" ]; then
  RIP=$(doctl compute reserved-ip create --droplet-id "$ID" --format IP --no-header)
fi

if ! doctl compute firewall list --format Name --no-header | grep -qx fb-web-fw; then
  doctl compute firewall create --name fb-web-fw --tag-names fb-web \
    --inbound-rules "protocol:tcp,ports:22,address:${SSH_ALLOW_IP}/32 protocol:tcp,ports:80,address:0.0.0.0/0,address:::/0 protocol:tcp,ports:443,address:0.0.0.0/0,address:::/0" \
    --outbound-rules "protocol:tcp,ports:all,address:0.0.0.0/0,address:::/0 protocol:udp,ports:all,address:0.0.0.0/0,address:::/0 protocol:icmp,address:0.0.0.0/0,address:::/0" >/dev/null
fi

echo "droplet=$ID reserved_ip=$RIP"
