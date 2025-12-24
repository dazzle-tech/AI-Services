# DigitalOcean Deployment Guide

Complete guide for deploying Clinical Summary Service to DigitalOcean.

## 🚀 Quick Start (5 Minutes)

1. **Push to GitHub:**

```bash
git init
git add .
git commit -m "Ready for deployment"
git remote add origin https://github.com/your-username/your-repo.git
git push -u origin main
```

2. **Deploy on DigitalOcean:**

   - Go to: https://cloud.digitalocean.com/apps
   - Create App → Connect GitHub repo
   - Set Run Command: `uvicorn main:app --host 0.0.0.0 --port 8080`
   - Add `OPENAI_API_KEY` as SECRET environment variable
   - Deploy!

3. **Done!** Your app: `https://your-app.ondigitalocean.app`

---

## Detailed Deployment Options

## 📋 Pre-Deployment Checklist

- [ ] Code is ready and tested locally
- [ ] OpenAI API key is available
- [ ] DigitalOcean account created
- [ ] Domain name (optional) ready

---

## 🚀 Option 1: DigitalOcean App Platform (Recommended)

### Step 1: Prepare Your Code

1. **Ensure all files are committed:**

```bash
cd summarization_service
git add .
git commit -m "Ready for deployment"
git push origin main
```

2. **Create `.do/app.yaml` file** (see below)

### Step 2: Create App Platform Configuration

Create file: `.do/app.yaml`

```yaml
name: clinical-summary-service
region: nyc
services:
  - name: api
    github:
      repo: your-username/your-repo
      branch: main
      deploy_on_push: true
    run_command: uvicorn main:app --host 0.0.0.0 --port 8080
    environment_slug: python
    instance_count: 1
    instance_size_slug: basic-xxs
    http_port: 8080
    routes:
      - path: /
    envs:
      - key: OPENAI_API_KEY
        scope: RUN_TIME
        type: SECRET
      - key: OPENAI_MODEL
        value: gpt-4o
      - key: OPENAI_TEMPERATURE
        value: "0.2"
      - key: API_HOST
        value: "0.0.0.0"
      - key: API_PORT
        value: "8080"
      - key: API_RELOAD
        value: "false"
    health_check:
      http_path: /api/v1/health
      initial_delay_seconds: 10
      period_seconds: 10
      timeout_seconds: 5
      success_threshold: 1
      failure_threshold: 3
```

### Step 3: Deploy via DigitalOcean Dashboard

1. **Go to DigitalOcean Dashboard**

   - Navigate to **Apps** → **Create App**

2. **Connect Repository**

   - Connect your GitHub/GitLab repository
   - Select the branch (usually `main`)

3. **Configure App**

   - App Platform will auto-detect Python
   - Set **Run Command:** `uvicorn main:app --host 0.0.0.0 --port 8080`
   - Set **HTTP Port:** `8080`

4. **Set Environment Variables**

   - Click **Environment Variables**
   - Add:
     - `OPENAI_API_KEY` (as SECRET)
     - `OPENAI_MODEL` = `gpt-4o`
     - `OPENAI_TEMPERATURE` = `0.2`
     - `API_HOST` = `0.0.0.0`
     - `API_PORT` = `8080`
     - `API_RELOAD` = `false`

5. **Configure Health Check**

   - Path: `/api/v1/health`
   - Initial Delay: 10 seconds

6. **Deploy**
   - Click **Create Resources**
   - Wait for deployment (5-10 minutes)

### Step 4: Access Your App

- Your app will be available at: `https://your-app-name.ondigitalocean.app`
- API endpoint: `https://your-app-name.ondigitalocean.app/api/v1/summarize`

---

## 🖥️ Option 2: DigitalOcean Droplet (VPS)

### Step 1: Create Droplet

1. **Create Droplet:**

   - Image: Ubuntu 22.04 LTS
   - Plan: Basic ($6/month minimum, 1GB RAM)
   - Region: Choose closest to users
   - Authentication: SSH keys (recommended)

2. **Note your Droplet IP address**

### Step 2: Connect to Droplet

```bash
ssh root@your-droplet-ip
```

### Step 3: Install Dependencies

```bash
# Update system
apt update && apt upgrade -y

# Install Python and pip
apt install -y python3 python3-pip python3-venv git

# Install nginx (for reverse proxy)
apt install -y nginx

# Install certbot (for SSL)
apt install -y certbot python3-certbot-nginx
```

### Step 4: Clone Your Code

```bash
# Create app directory
mkdir -p /opt/clinical-summary-service
cd /opt/clinical-summary-service

# Clone your repository (or upload files)
git clone https://github.com/your-username/your-repo.git .
# OR use SCP to upload files from local machine
```

### Step 5: Set Up Python Environment

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 6: Configure Environment Variables

```bash
# Create .env file
nano .env
```

Add:

```env
OPENAI_API_KEY=sk-your-actual-key-here
OPENAI_MODEL=gpt-4o
OPENAI_TEMPERATURE=0.2
API_HOST=0.0.0.0
API_PORT=8003
API_RELOAD=false
```

Save and exit (Ctrl+X, Y, Enter)

### Step 7: Create Systemd Service

```bash
# Create service file
nano /etc/systemd/system/clinical-summary.service
```

Add:

```ini
[Unit]
Description=Clinical Summary Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/clinical-summary-service
Environment="PATH=/opt/clinical-summary-service/venv/bin"
ExecStart=/opt/clinical-summary-service/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8003
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
systemctl daemon-reload
systemctl enable clinical-summary
systemctl start clinical-summary
systemctl status clinical-summary
```

### Step 8: Configure Nginx Reverse Proxy

```bash
# Create nginx config
nano /etc/nginx/sites-available/clinical-summary
```

Add:

```nginx
server {
    listen 80;
    server_name your-domain.com;  # or your droplet IP

    location / {
        proxy_pass http://127.0.0.1:8003;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable:

```bash
ln -s /etc/nginx/sites-available/clinical-summary /etc/nginx/sites-enabled/
nginx -t
systemctl restart nginx
```

### Step 9: Set Up SSL (Optional but Recommended)

```bash
# If you have a domain
certbot --nginx -d your-domain.com

# Follow prompts to get SSL certificate
```

### Step 10: Configure Firewall

```bash
# Allow SSH, HTTP, HTTPS
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```

---

## 🐳 Option 3: Docker Deployment

### Step 1: Create Dockerfile

Create `Dockerfile` in project root (see below)

### Step 2: Create docker-compose.yml

```yaml
version: "3.8"

services:
  api:
    build: .
    ports:
      - "8003:8003"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - OPENAI_MODEL=gpt-4o
      - OPENAI_TEMPERATURE=0.2
      - API_HOST=0.0.0.0
      - API_PORT=8003
      - API_RELOAD=false
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8003/api/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Step 3: Deploy on Droplet

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Install Docker Compose
apt install -y docker-compose

# Clone/upload code
cd /opt/clinical-summary-service

# Create .env file with OPENAI_API_KEY

# Build and run
docker-compose up -d

# Check logs
docker-compose logs -f
```

---

## 🔒 Production Security Checklist

### 1. Environment Variables

- ✅ Never commit `.env` file
- ✅ Use DigitalOcean Secrets/Environment Variables
- ✅ Rotate API keys regularly

### 2. CORS Configuration

Update `main.py` to restrict CORS:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-frontend-domain.com"],  # Specific domains
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

### 3. Rate Limiting (Recommended)

Add rate limiting to prevent abuse:

```bash
pip install slowapi
```

### 4. HTTPS Only

- ✅ Use SSL/TLS (Let's Encrypt via Certbot)
- ✅ Redirect HTTP to HTTPS

### 5. Monitoring

- ✅ Set up health check endpoint
- ✅ Monitor logs: `journalctl -u clinical-summary -f`
- ✅ Set up alerts for downtime

---

## 📝 Required Files for Deployment

### 1. `.do/app.yaml` (App Platform)

See configuration above

### 2. `Dockerfile` (Docker deployment)

See below

### 3. `.dockerignore`

```
__pycache__
*.pyc
*.pyo
*.pyd
.Python
env/
venv/
.venv/
.env
.git
.gitignore
*.md
tests/
.pytest_cache/
```

### 4. `Procfile` (Alternative for App Platform)

```
web: uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
```

---

## 🔍 Post-Deployment Testing

### 1. Health Check

```bash
curl https://your-app.ondigitalocean.app/api/v1/health
```

### 2. Test Summary Generation

```bash
curl -X POST https://your-app.ondigitalocean.app/api/v1/summarize \
  -H "Content-Type: application/json" \
  -d '{
    "patient_data": {
      "Age": "45 years",
      "Gender": "Male",
      "Diagnosis": "Diabetes"
    }
  }'
```

### 3. Check Logs

**App Platform:**

- Dashboard → Runtime Logs

**Droplet:**

```bash
journalctl -u clinical-summary -f
# or
docker-compose logs -f
```

---

## 🐛 Troubleshooting

### Service Won't Start

```bash
# Check service status
systemctl status clinical-summary

# Check logs
journalctl -u clinical-summary -n 50

# Check if port is in use
netstat -tulpn | grep 8003
```

### 502 Bad Gateway (Nginx)

- Check if service is running: `systemctl status clinical-summary`
- Check nginx error logs: `tail -f /var/log/nginx/error.log`
- Verify proxy_pass URL matches service port

### OpenAI API Errors

- Verify `OPENAI_API_KEY` is set correctly
- Check API key is valid and has credits
- Review service logs for detailed error messages

### High Memory Usage

- Consider upgrading Droplet plan
- Monitor with: `htop` or `free -h`
- Optimize by reducing `openai_max_tokens` if needed

---

## 💰 Cost Estimation

### App Platform

- **Basic:** $5/month (512MB RAM)
- **Professional:** $12/month (1GB RAM) - Recommended

### Droplet

- **Basic:** $6/month (1GB RAM, 1 vCPU)
- **Regular:** $12/month (2GB RAM, 1 vCPU) - Recommended

### Additional Costs

- OpenAI API: ~$0.01 per summary (varies by usage)
- Domain: ~$12/year (optional)

---

## 📚 Next Steps

1. ✅ Deploy using one of the methods above
2. ✅ Test all endpoints
3. ✅ Set up monitoring
4. ✅ Configure custom domain (optional)
5. ✅ Set up CI/CD for automatic deployments

---

## 🆘 Support

If you encounter issues:

1. Check service logs
2. Verify environment variables
3. Test health endpoint
4. Review DigitalOcean documentation

Good luck with your deployment! 🚀
