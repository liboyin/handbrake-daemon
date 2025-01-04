#!/bin/bash

set -euo pipefail

PIP_CONF_PATH=$HOME/.pip/pip.conf
mkdir -p "$(dirname "$PIP_CONF_PATH")"
cat <<EOF > "$PIP_CONF_PATH"
[global]
disable-pip-version-check = true
no-cache-dir = true
root-user-action = ignore
EOF

# Configure PyPI proxy if defined
if [ -v PYPI_PROXY ]; then
    cat <<EOF >> "$PIP_CONF_PATH"
index-url = $PYPI_PROXY
trusted-host = $(echo "$PYPI_PROXY" | sed -E 's|https?://([^:/]+).*|\1|')
EOF
fi

cat "$PIP_CONF_PATH"

# pyproject.toml requires setuptools >= 64 but python3-setuptools is too old on APT
curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
python get-pip.py
rm get-pip.py

# Pin dependency versions by installing from the lock file before installing this project
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
fi
pip install -e .

# Remove pip cache
pip_cache_dirs=(
    "/tmp/pip-tmp"
    "$HOME/.cache/pip"
)
for dir_path in "${pip_cache_dirs[@]}"; do
    if [ -d "$dir_path" ]; then
        echo "Removing pip cache dir: $dir_path"
        rm -rf "$dir_path"
    fi
done
