#!/bin/bash
apt-get update
apt-get install -y chromium chromium-driver
ln -sf /usr/bin/chromium /usr/bin/chromium-browser
ln -sf /usr/bin/chromedriver /usr/bin/chromedriver
