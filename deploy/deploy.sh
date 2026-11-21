#!/usr/bin/env bash
# Upload public/ to the droplet as a new release and switch the "current" symlink.
# Usage: HOST=<droplet ip> ./deploy/deploy.sh   (run from repo root after hugo build)
set -euo pipefail
HOST="${HOST:?set HOST to the droplet address}"
KEY="${KEY:-$HOME/.ssh/id_ed25519_fbweb}"
KEEP="${KEEP:-5}"
TS=$(date -u +%Y%m%d%H%M%S)
SSH=(ssh -i "$KEY" -o BatchMode=yes "deploy@$HOST")

[ -f public/index.html ] || { echo "public/index.html missing: run hugo first"; exit 1; }
tar -C public -czf - . | "${SSH[@]}" "set -e; R=/srv/firebirdsql/releases/$TS; mkdir -p \$R; tar -C \$R -xzf -; \
  ln -sfn \$R /srv/firebirdsql/current.new && mv -T /srv/firebirdsql/current.new /srv/firebirdsql/current; \
  sudo /usr/sbin/nginx -t; sudo /usr/bin/systemctl reload nginx; \
  ls -1dt /srv/firebirdsql/releases/* | tail -n +$((KEEP+1)) | xargs -r rm -rf; echo deployed \$R"
