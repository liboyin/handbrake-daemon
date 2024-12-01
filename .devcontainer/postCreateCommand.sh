#! /bin/bash
pip freeze | grep -v "handbrake-daemon\|handbrake_daemon" > requirements.txt
# deployment dependencies are installed as user, but current user is vscode
sudo pip --disable-pip-version-check --no-cache-dir install -e .[dev]
