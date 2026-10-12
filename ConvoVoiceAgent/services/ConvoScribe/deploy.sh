#!/bin/bash
# Deployment script for ConvoScribe

set -e

echo "Starting ConvoScribe deployment..."

APP_DIR="/opt/convoscribe-service"

apt update && apt install -y python3 python3-pip python3-venv git nginx

mkdir -p "$APP_DIR"
cd "$APP_DIR"

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

cat > /etc/systemd/system/convoscribe.service << EOF
[Unit]
Description=ConvoScribe Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
ExecStart=$APP_DIR/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8026
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable convoscribe
systemctl start convoscribe

echo "Deployment complete. Create .env in $APP_DIR and configure nginx as needed."
