#! /bin/bash
# deployment dependencies are installed as root, but current user is ubuntu
sudo pip install -r requirements.txt
sudo pip install -r requirements-dev.txt
# use native installer of Claude Code
curl -fsSL https://claude.ai/install.sh | bash
# install nodeJS + Gemini CLI
sudo apt-get update
curl -fsSL https://deb.nodesource.com/setup_25.x | sudo -E bash -
sudo apt-get install -y --no-install-recommends nodejs
sudo npm install -g @google/gemini-cli
