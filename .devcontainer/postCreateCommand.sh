#! /bin/bash
pip freeze | grep -v "handbrake-daemon\|handbrake_daemon" > requirements.txt
# deployment dependencies are installed as root, but current user is ubuntu
sudo pip install -e .[dev]
# install nodeJS for AI code assistants
sudo apt-get update
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y --no-install-recommends nodejs
# npx https://github.com/google-gemini/gemini-cli
# npx @anthropic-ai/claude-code
