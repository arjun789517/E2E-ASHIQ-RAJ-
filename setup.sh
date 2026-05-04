#!/bin/bash

# Update and install Chromium & Chromedriver on Render's Ubuntu environment
apt-get update
apt-get install -y chromium chromium-driver

# Create symlinks so the app finds them at standard paths
ln -sf /usr/bin/chromium /usr/bin/chromium-browser
ln -sf /usr/bin/chromedriver /usr/bin/chromedriver

# Verify installation
chromium --version
chromedriver --version

echo "✅ Chrome/Chromium setup complete"
