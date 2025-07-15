#! /bin/bash
pip freeze | grep -v "handbrake-daemon\|handbrake_daemon" > requirements.txt
# deployment dependencies are installed as root, but current user is ubuntu
sudo pip install -e .[dev]
# install nodeJS for AI code assistants
sudo apt-get update
sudo apt-get install -y --no-install-recommends nodejs npm
# npx @google/gemini-cli
# npx @anthropic-ai/claude-code
