# Production Cloud Deployment Guide

AuraRAG is fully containerized and can be deployed to any Docker-supporting cloud host.

---

## 1. Single-Server Deployment (Docker Compose)

The easiest deployment method is running the standard `docker-compose` setup on a single VPS (DigitalOcean, Linode, AWS EC2, etc.):

1. Clone your files to the server.
2. Edit `.env` configurations (Set `GROQ_API_KEY`, `JWT_SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`).
3. Start in daemon mode:
   ```bash
   docker-compose up -d --build
   ```
4. Map your domain using external setups or let Nginx listen directly on port 80.

---

## 2. Serverless Cloud Deployment (Render / Railway)

To deploy to serverless infrastructure with separate databases:

### Backend Service (FastAPI)
1. Set start command to:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```
2. Provision a managed **PostgreSQL** database and pass connection URL as env variable `DATABASE_URL`.
3. Provision a managed **Redis** database and pass URL as env `REDIS_URL`.
4. Configure environment variables (`GROQ_API_KEY`, `JWT_SECRET_KEY`).
5. Map persistent disk volume at `/app/uploads` and `/app/vector_store` so file indexes are retained when container updates or restarts.

### Frontend Service (React SPA)
1. Deploy as a Static Site or Docker Web Service pointing to `./frontend` sub-directory.
2. Set build command to `npm run build` and publish directory to `dist`.
3. Configure rewriting rules: map all `/api/*` requests to the Backend Service URL, and fallback all other pages to `/index.html` to support React client routing.
