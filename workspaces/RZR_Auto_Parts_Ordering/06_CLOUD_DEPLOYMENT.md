# 06 — Cloud Deployment & Infrastructure

## Hosting Architecture

```
┌─────────────────────────────────────────────────────┐
│                 Google Cloud Platform                 │
│                                                       │
│  ┌─────────────────┐    ┌─────────────────────────┐  │
│  │  Cloud Run       │    │  Cloud Storage           │  │
│  │  (FastAPI +      │    │  (Service manuals,       │  │
│  │   React SPA)     │    │   schematics, processed  │  │
│  │                  │    │   documents)              │  │
│  │  Auto-scaling    │    └─────────────────────────┘  │
│  │  0 → N instances │                                 │
│  └────────┬────────┘                                  │
│           │                                           │
│           ▼                                           │
│  ┌─────────────────┐    ┌───────────────────────┐    │
│  │  Supabase        │    │  Secret Manager        │   │
│  │  (Managed)       │    │  (API keys, dealer     │   │
│  │                  │    │   credentials)          │   │
│  │  • PostgreSQL    │    └───────────────────────┘    │
│  │  • pgvector      │                                 │
│  │  • Auth          │    ┌───────────────────────┐    │
│  │  • Edge Funcs    │    │  Cloud Scheduler       │   │
│  └─────────────────┘    │  (Catalog sync jobs)   │   │
│                          └───────────────────────┘    │
└─────────────────────────────────────────────────────┘
```

### Why Google Cloud Run?

| Feature | Benefit |
|---------|---------|
| **Container-based** | Docker image with all dependencies, reproducible |
| **Auto-scaling** | Scales to zero when no one's using it (cost savings) |
| **HTTPS built-in** | Automatic TLS certificates, custom domain support |
| **Gemini integration** | Same GCP project, no cross-cloud API calls |
| **Pay-per-use** | Only charged for actual compute time |

### Estimated Monthly Cost

| Service | Specification | Est. Cost/mo |
|---------|--------------|-------------|
| Cloud Run | 1 vCPU, 2GB RAM, ~100 hrs/mo usage | $15-30 |
| Supabase | Pro plan (8GB DB, pgvector) | $25 |
| Cloud Storage | ~10GB for documents/schematics | $0.50 |
| Gemini API | ~50k tokens/day avg (chat + embeddings) | $30-60 |
| Secret Manager | Minimal usage | $0.06 |
| Custom Domain | Via Google Domains or Cloudflare | $12/yr |
| **TOTAL** | | **~$75-120/mo** |

---

## Security & Access Control

### Authentication
- Supabase Auth with email/password login
- Only authorized mechanics can access the system
- Admin role for managing users, viewing all orders

### Access Tiers
```
MECHANIC
├── Select vehicles
├── Chat with AI
├── Edit parts lists
├── Submit orders (with approval)
└── View own order history

LEAD MECHANIC / MANAGER
├── Everything above, plus:
├── Approve orders over threshold
├── View all mechanics' orders
├── Access repair analytics
└── Manage fleet vehicles

ADMIN
├── Everything above, plus:
├── Manage user accounts
├── Configure AI settings
├── Access document ingestion tools
└── View system logs
```

### Data Security
- All data encrypted at rest (Supabase default)
- HTTPS for all traffic (Cloud Run default)
- Polaris dealer credentials stored in GCP Secret Manager
- Row-Level Security (RLS) on Supabase tables
- No PII beyond mechanic names

---

## CI/CD Pipeline

```
GitHub Push → GitHub Actions → Build Docker Image → Deploy to Cloud Run
                    │
                    ├── Run tests
                    ├── Build React frontend (Vite)
                    ├── Build Docker image
                    ├── Push to Google Artifact Registry
                    └── Deploy to Cloud Run (rolling update)
```

### Dockerfile
```dockerfile
FROM python:3.12-slim

# Install Node.js for frontend build
RUN apt-get update && apt-get install -y nodejs npm

# Build frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Install Python dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (for portal agent)
RUN playwright install chromium --with-deps

# Copy application code
COPY api/ ./api/
COPY agent/ ./agent/
COPY knowledge/ ./knowledge/
COPY shared/ ./shared/

# Serve React SPA from FastAPI
# Frontend build output goes to /app/frontend/dist
# FastAPI serves it as static files

EXPOSE 8080
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

---

## Monitoring & Observability

| Tool | Purpose |
|------|---------|
| **Cloud Run Metrics** | CPU, memory, request count, latency |
| **Structured Logging** | JSON logs to Cloud Logging (reuse `bot_logger.py` pattern) |
| **Slack Alerts** | Order submissions, failures, low-confidence diagnoses |
| **Supabase Dashboard** | Database health, query performance |
| **Uptime Checks** | Cloud Monitoring ping every 5 min |

---

*Continue to → [07_IMPLEMENTATION_ROADMAP.md](./07_IMPLEMENTATION_ROADMAP.md)*
