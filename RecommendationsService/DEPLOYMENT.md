# DigitalOcean Deployment Guide - Recommendations Service

Complete guide for deploying Clinical Recommendations Service to DigitalOcean.

## 🚀 Quick Start

### Option 1: DigitalOcean App Platform (Recommended)

1. **Push to GitHub:**
```bash
git add .
git commit -m "Add recommendations service"
git push origin main
```

2. **Deploy on DigitalOcean:**
   - Go to: https://cloud.digitalocean.com/apps
   - Create App → Connect GitHub repo
   - Select `recommendations_service` directory
   - Set Run Command: `uvicorn main:app --host 0.0.0.0 --port 8080`
   - Add `OPENAI_API_KEY` as SECRET environment variable
   - Deploy!

3. **Done!** Your app: `https://your-app.ondigitalocean.app`

### Option 2: Docker Deployment

**Build and run with Docker:**
```bash
docker build -t clinical-recommendations-service .
docker run -p 8007:8007 --env-file .env clinical-recommendations-service
```

**Or use Docker Compose:**
```bash
docker-compose up -d
```

### Option 3: DigitalOcean Droplet

**Using deploy.sh script:**
```bash
chmod +x deploy.sh
sudo ./deploy.sh
```

Then:
1. Copy your code to `/opt/clinical-recommendations-service`
2. Create `.env` file with `OPENAI_API_KEY`
3. Start service: `systemctl start clinical-recommendations`

## 📋 Configuration

### Environment Variables

Required:
- `OPENAI_API_KEY` - Your OpenAI API key

Optional:
- `OPENAI_MODEL` - Default: `qwen3:1.7b`
- `OPENAI_TEMPERATURE` - Default: `0.3`
- `OPENAI_MAX_TOKENS` - Default: `1500`
- `API_PORT` - Default: `8007` (or `8080` for App Platform)

## 🔍 Health Check

After deployment, verify:
- Health endpoint: `https://your-app.ondigitalocean.app/api/v1/health`
- API docs: `https://your-app.ondigitalocean.app/docs`

## 📝 Files Included

- `Dockerfile` - Docker container configuration
- `docker-compose.yml` - Docker Compose setup
- `.do/app.yaml` - DigitalOcean App Platform config
- `Procfile` - Process file for App Platform
- `deploy.sh` - Droplet deployment script
- `.dockerignore` - Docker ignore rules

---

**Ready to deploy!** 🚀




