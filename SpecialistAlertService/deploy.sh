#!/bin/bash
# Deployment script for Specialist Alert Service

set -e

echo "Starting deployment..."

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (use sudo)"
    exit 1
fi

echo -e "${YELLOW}Updating system...${NC}"
apt update && apt upgrade -y

echo -e "${YELLOW}Installing dependencies...${NC}"
apt install -y python3 python3-pip python3-venv git nginx certbot python3-certbot-nginx

APP_DIR="/opt/specialist-alert-service"
echo -e "${YELLOW}Setting up application directory...${NC}"
mkdir -p $APP_DIR
cd $APP_DIR

echo -e "${YELLOW}Creating virtual environment...${NC}"
python3 -m venv venv
source venv/bin/activate

echo -e "${YELLOW}Installing Python dependencies...${NC}"
pip install --upgrade pip
pip install -r requirements.txt

echo -e "${YELLOW}Creating systemd service...${NC}"
cat > /etc/systemd/system/specialist-alert.service << EOF
[Unit]
Description=Specialist Alert Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
ExecStart=$APP_DIR/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8014
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable specialist-alert
systemctl start specialist-alert

echo -e "${YELLOW}Configuring firewall...${NC}"
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 8014/tcp
ufw --force enable

echo -e "${GREEN}Deployment complete!${NC}"
echo ""
echo "Next steps:"
echo "1. Create .env file in $APP_DIR with OPENAI_API_KEY"
echo "2. Configure nginx reverse proxy"
echo "3. Set up SSL with certbot if you have a domain"
echo ""
echo "Check service status: systemctl status specialist-alert"
echo "View logs: journalctl -u specialist-alert -f"
