# PetsApp Deployment Guide

## Prerequisites
- Docker installed (for local testing)
- Git repo pushed to GitHub
- One of: Fly.io, Google Cloud Run, or Render account

---

## Option 1: Deploy to Fly.io (Recommended for Speed)

### Steps
1. Install Fly CLI: https://fly.io/docs/getting-started/installing-flyctl/
2. Authenticate:
   ```bash
   flyctl auth login
   ```
3. Create app (first time only):
   ```bash
   flyctl apps create petsapp
   ```
4. Set secrets:
   ```bash
   flyctl secrets set SECRET_KEY="your-secret-key"
   flyctl secrets set SQLALCHEMY_DATABASE_URI="mysql+pymysql://user:pass@host:3306/dbname"
   ```
5. Deploy:
   ```bash
   flyctl deploy
   ```
6. View logs:
   ```bash
   flyctl logs
   ```

---

## Option 2: Deploy to Google Cloud Run

### Steps
1. Install Google Cloud SDK: https://cloud.google.com/sdk/docs/install
2. Authenticate and set project:
   ```bash
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID
   ```
3. Enable Cloud Build and Cloud Run APIs:
   ```bash
   gcloud services enable cloudbuild.googleapis.com run.googleapis.com
   ```
4. Deploy (creates image + service):
   ```bash
   gcloud builds submit --config cloudbuild.yaml
   ```
5. View service and set env vars in Cloud Console or via CLI:
   ```bash
   gcloud run services update petsapp --region us-central1 --set-env-vars SECRET_KEY="...",SQLALCHEMY_DATABASE_URI="..."
   ```

---

## Option 3: Deploy to Render

### Steps
1. Sign up at https://render.com
2. Create a new "Web Service" in Render dashboard
3. Connect GitHub repo
4. Render auto-detects `render.yaml`
5. Add environment variables in Render dashboard:
   - `SECRET_KEY`
   - `SQLALCHEMY_DATABASE_URI`
6. Click "Deploy" — Render will build and launch

---

## Important Production Checklist

Before deploying to any platform:

- [ ] Database: Set up managed MySQL (RDS, Render DB, Cloud SQL)
- [ ] Secrets: Never commit `.env` or hardcode creds; use platform env vars
- [ ] Media uploads: Configure S3, GCS, or cloud storage (media/ folder won't persist on ephemeral instances)
- [ ] Flask config: Update `config.py` to read from env vars:
  ```python
  import os
  SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key")
  SQLALCHEMY_DATABASE_URI = os.environ.get("SQLALCHEMY_DATABASE_URI", "sqlite:///dev.db")
  ```
- [ ] Migrations: Run `flask db upgrade` on first deploy (one-off command or startup hook)
- [ ] Debug mode: Set `FLASK_ENV=production` (already in configs above)

---

## Troubleshooting

- **Port not binding**: Ensure app listens on `0.0.0.0:5000` (Dockerfile CMD does this)
- **Database connection fails**: Check credentials and network access (Cloud SQL proxy, security groups, etc.)
- **Socket.IO issues**: Ensure eventlet is used (`gunicorn -k eventlet`); check CORS settings in `app.py`
- **Persistent storage**: Don't rely on `/app/media` — use S3 or equivalent

Pick one platform and I'll give you exact next steps!
