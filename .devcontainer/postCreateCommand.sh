#! /bin/bash
pip freeze | grep -v "handbrake-daemon\|handbrake_daemon" > requirements.txt
# deployment dependencies are installed as root, but current user is ubuntu
sudo pip --disable-pip-version-check --no-cache-dir install -e .[dev]
