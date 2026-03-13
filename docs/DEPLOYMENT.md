# Deployment Guide — War Games

Production deployment: **Vercel** (frontend) + **Fly.io** (backend) + **Supabase** (auth/DB).

---

## Architecture

```text
Browser
  │
  ├─── HTTPS ──► Vercel CDN (Vue SPA, static files)
  │                │
  │                │  VITE_API_BASE (build-time env var)
  │                ▼
  └─── HTTPS ──► Fly.io (FastAPI + Docker, persistent VM)
                   │
                   ├──► Supabase PostgreSQL (DATABASE_URL)
                   └──► LLM Proxy (LLM_BASE_URL)
```

**Why this split:**

- **Vercel** serves the static Vue bundle from edge CDN — zero config, fast, free.
- **Fly.io** runs the backend in a persistent VM. SSE debate streams can last 10–60 minutes; serverless would time out. Free allowance covers small apps.
- All API calls (including SSE) go **browser → Fly.io directly**. There is no Vercel proxy in the path.

---

## 1. Fly.io — Backend

### 1.1 Prerequisites

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Login
fly auth login
```

### 1.2 App

The app `a2a-war-games` is already created at [fly.io/apps/a2a-war-games](https://fly.io/apps/a2a-war-games).

`fly.toml` is checked into the repo root — Fly.io uses it automatically.

Key settings already configured:

- **Dockerfile** build
- `min_machines_running = 1` — keeps 1 VM always on (required for SSE)
- `memory = 256mb` — free tier limit
- Health check on `GET /api/health`

### 1.3 Set secrets (environment variables)

Secrets are set once via CLI and persisted in Fly.io's secret store:

```bash
fly secrets set \
  LLM_BASE_URL="https://your-llm-proxy/v1" \
  LLM_API_KEY="<your key>" \
  LLM_DEFAULT_MODEL="<default model slug>" \
  LLM_COUNCIL_MODELS="<comma-separated council model slugs>" \
  LLM_CHAIRMAN_MODEL="<chairman model slug>" \
  DATABASE_URL="postgresql://postgres:<password>@<host>:5432/postgres" \
  ALLOWED_ORIGINS="https://your-app.vercel.app" \
  SUPABASE_URL="https://your-project.supabase.co" \
  SUPABASE_ANON_KEY="<anon key>" \
  SUPABASE_SERVICE_KEY="<service role key>" \
  SUPABASE_JWT_SECRET="<JWT secret>" \
  -a a2a-war-games
```

### 1.4 Deploy

```bash
fly deploy -a a2a-war-games
```

Fly.io builds the Docker image and deploys it. Subsequent pushes to `main` can be auto-deployed via GitHub Actions (optional).

**Note:** `--workers 1` is enforced by `railway.json` (kept as alternative) and should also be used here. The engine registry (`_running_engines`) is an in-process dict; multiple workers would break session routing. The default `CMD` in `Dockerfile` uses a single worker — do not override.

### 1.5 Get your Fly.io URL

The public URL is: `https://a2a-war-games.fly.dev`

Use this as `VITE_API_BASE` in Vercel (step 2.2).

### 1.6 Useful commands

```bash
fly logs -a a2a-war-games          # tail logs
fly status -a a2a-war-games        # machine status
fly ssh console -a a2a-war-games   # SSH into the VM
fly deploy -a a2a-war-games        # redeploy
```

---

## 2. Vercel — Frontend

### 2.1 Create project

1. Go to [vercel.com](https://vercel.com) → **Add New Project** → import this GitHub repo
2. Vercel auto-detects `vercel.json` at the repo root

Settings already configured in `vercel.json`:

- **Build command:** `cd frontend && npm install && npm run build`
- **Output directory:** `frontend/dist`
- **SPA fallback:** all non-asset routes rewrite to `/index.html`
- **Asset caching:** 1-year immutable cache on `/assets/`

### 2.2 Environment variables

Set these in Vercel → your project → **Settings** → **Environment Variables**:

```env
# Supabase (same project as backend)
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=<anon key>

# Fly.io backend URL
VITE_API_BASE=https://a2a-war-games.fly.dev
```

**Important:** `VITE_API_BASE` is baked into the JS bundle at build time. After changing it, trigger a redeploy.

### 2.3 Deploy

Vercel deploys automatically on every push to `main`.

---

## 3. Supabase — Auth & Database

### 3.1 OAuth callback URLs

1. Supabase Dashboard → **Authentication** → **URL Configuration**
2. **Site URL:** `https://your-app.vercel.app`
3. **Redirect URLs:** add `https://your-app.vercel.app/**`

### 3.2 CORS (Backend)

After the first Fly.io deploy, update `ALLOWED_ORIGINS` to match your Vercel domain:

```bash
fly secrets set ALLOWED_ORIGINS="https://your-app.vercel.app" -a a2a-war-games
```

This triggers an automatic redeploy.

---

## 4. Seed Demo Projects

After the first successful backend deploy, seed the 3 demo projects (Philosophy, Geopolitics, Psychology):

```bash
curl -X POST https://a2a-war-games.fly.dev/api/projects/seed-demo
```

This is idempotent — safe to call multiple times.

---

## 5. Verification Checklist

- [ ] `GET https://a2a-war-games.fly.dev/api/health` returns `{"status": "ok"}`
- [ ] Vercel build completes without errors
- [ ] Opening `https://your-app.vercel.app` loads the landing page
- [ ] Direct URL access (e.g. `/projects`) works (SPA fallback)
- [ ] Login with Google OAuth works (Supabase callback URLs set)
- [ ] Creating a project and running a session works end-to-end
- [ ] SSE stream stays connected during a full debate round
- [ ] Demo projects appear in the Community tab (after seeding)

---

## 6. Self-Hosted Alternative

A `docker-compose.yml` is included for running both services locally or on a VPS:

```bash
# Copy and fill in your env vars
cp .env.example .env
# edit .env

# Start everything
docker compose up -d

# Backend: http://localhost:8000
# Frontend: http://localhost:80
```

The compose stack includes:

- `backend` — FastAPI on port 8000
- `frontend` — nginx serving the built Vue app on port 80, proxying `/api/` to backend

See `nginx.conf` for the proxy configuration.

---

## 7. Environment Variable Reference

### Backend (Fly.io secrets)

| Variable | Required | Description |
| -------- | -------- | ----------- |
| `LLM_BASE_URL` | yes | LLM proxy base URL |
| `LLM_API_KEY` | yes | LLM proxy API key |
| `LLM_DEFAULT_MODEL` | yes | Default model slug |
| `LLM_COUNCIL_MODELS` | yes | Comma-separated council model slugs |
| `LLM_CHAIRMAN_MODEL` | yes | Chairman model slug |
| `DATABASE_URL` | yes | PostgreSQL connection string (Supabase) |
| `ALLOWED_ORIGINS` | yes | CORS allowed origins (Vercel domain) |
| `SUPABASE_URL` | yes | Supabase project URL |
| `SUPABASE_ANON_KEY` | yes | Supabase anon key |
| `SUPABASE_SERVICE_KEY` | yes | Supabase service role key |
| `SUPABASE_JWT_SECRET` | yes | Supabase JWT secret |
| `DEBUG` | no | Set in `fly.toml` [env] — `false` in production |

### Frontend (Vercel build-time)

| Variable | Required | Description |
| -------- | -------- | ----------- |
| `VITE_SUPABASE_URL` | yes | Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | yes | Supabase anon key |
| `VITE_API_BASE` | yes | Fly.io backend public URL |
