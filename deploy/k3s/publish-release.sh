#!/usr/bin/env bash
# Runs in GitHub Actions after the unit and PostgreSQL integration tests.
set -Eeuo pipefail
: "${DEPLOY_REVISION:?}"
: "${VPS_SSH_KEY:?}"
: "${VPS_KNOWN_HOSTS:?}"
[[ "$DEPLOY_REVISION" =~ ^[0-9a-f]{40}$ ]]
[[ "$(git rev-parse HEAD)" == "$DEPLOY_REVISION" ]]

ssh_dir=$(mktemp -d)
trap 'rm -rf -- "$ssh_dir"' EXIT
chmod 700 "$ssh_dir"
printf '%s\n' "$VPS_SSH_KEY" > "$ssh_dir/key"
printf '%s\n' "$VPS_KNOWN_HOSTS" > "$ssh_dir/known_hosts"
chmod 600 "$ssh_dir/key" "$ssh_dir/known_hosts"

python3 - <<'PY'
import json
import os
from pathlib import Path
Path('web/static/version.json').write_text(json.dumps({'revision': os.environ['DEPLOY_REVISION']}))
PY

docker build --label "org.opencontainers.image.revision=$DEPLOY_REVISION" \
    -f backend/Dockerfile -t "melawdy-api:$DEPLOY_REVISION" .
docker build --label "org.opencontainers.image.revision=$DEPLOY_REVISION" \
    -f web/Dockerfile -t "melawdy-web:$DEPLOY_REVISION" web

echo 'Preparing compressed release archive'
docker save "melawdy-api:$DEPLOY_REVISION" "melawdy-web:$DEPLOY_REVISION" | gzip -6 > "$ssh_dir/images.tar.gz"
echo "Uploading release archive: $(wc -c < "$ssh_dir/images.tar.gz") bytes"
ssh -F /dev/null -i "$ssh_dir/key" -o IdentitiesOnly=yes -o BatchMode=yes \
        -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$ssh_dir/known_hosts" \
        -o ConnectTimeout=60 -o ServerAliveInterval=10 -o ServerAliveCountMax=6 \
        root@193.233.18.123 "deploy $DEPLOY_REVISION" < "$ssh_dir/images.tar.gz"
