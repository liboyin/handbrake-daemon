#!/bin/bash

# Configure PyPI proxy
if [ -n "$PYPI_PROXY" ]; then
    PIP_CONF_PATH=$HOME/.pip/pip.conf
    mkdir -p "$(dirname "$PIP_CONF_PATH")"
    cat <<EOF > "$PIP_CONF_PATH"
[global]
index-url = $PYPI_PROXY
trusted-host = $(echo "$PYPI_PROXY" | sed -E 's|https?://([^:/]+).*|\1|')
EOF
    cat "$PIP_CONF_PATH"
fi

# Pin dependency versions by installing from the lock file before installing this project
if [ -f "requirements.txt" ]; then
    pip --disable-pip-version-check --no-cache-dir install -r requirements.txt
fi
pip --disable-pip-version-check --no-cache-dir install -e .

pip_cache_dirs=(
    "/tmp/pip-tmp"
    "$HOME/.cache/pip"
    "$XDG_CACHE_HOME/pip"
)
for dir_path in "${pip_cache_dirs[@]}"; do
    if [ -d "$dir_path" ]; then
        echo "Removing pip cache dir: $dir_path"
        rm -rf "$dir_path"
    fi
done
