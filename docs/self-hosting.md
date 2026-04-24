# Self-Hosting BeLLMark

BeLLMark runs as a single Docker container with SQLite storage. No Redis, no Postgres, no external dependencies.

## Quick Start (Docker)

```bash
# 1. Create a directory and config
mkdir bellmark && cd bellmark
curl -O https://raw.githubusercontent.com/Context-Management/BeLLMark/main/docker-compose.yml
curl -O https://raw.githubusercontent.com/Context-Management/BeLLMark/main/.env.example
cp .env.example .env

# 2. Generate a secret key
echo "BELLMARK_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" >> .env

# 3. Add at least one LLM provider key to .env
# Edit .env and set OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.

# 4. Start
docker compose up -d

# 5. Open http://localhost:8000
```

That's it. BeLLMark is running.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BELLMARK_SECRET_KEY` | **Yes** | — | Encryption key for stored API keys. Generate with `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'` |
| `BELLMARK_API_KEY` | No | — | When set, all `/api/*` endpoints require this key in the `Authorization` header |
| `BELLMARK_DEV_MODE` | No | — | Set to `true` to skip API key auth (local dev only) |
| `BACKEND_PORT` | No | `8000` | Port the app listens on |
| `ALLOWED_ORIGINS` | No | localhost | CORS origins. Leave unset for localhost defaults, set to your domain for remote access |
| `ANTHROPIC_API_KEY` | No | — | Anthropic (Claude) API key |
| `OPENAI_API_KEY` | No | — | OpenAI API key |
| `GOOGLE_API_KEY` | No | — | Google (Gemini) API key |
| `OPENROUTER_API_KEY` | No | — | OpenRouter API key |
| `MISTRAL_API_KEY` | No | — | Mistral API key |
| `DEEPSEEK_API_KEY` | No | — | DeepSeek API key |
| `GROK_API_KEY` | No | — | Grok (xAI) API key |
| `GLM_API_KEY` | No | — | GLM (Zhipu) API key |
| `KIMI_API_KEY` | No | — | Kimi (Moonshot) API key |

You don't need all provider keys — just the ones you want to benchmark. You can also add keys through the UI after starting.

## Authentication Modes

BeLLMark has two auth modes, controlled by `BELLMARK_API_KEY` and `BELLMARK_DEV_MODE`:

| BELLMARK_API_KEY | BELLMARK_DEV_MODE | Behavior |
|------------------|-------------------|----------|
| Set | — | All API calls require `Authorization: Bearer <key>` header |
| Unset | `true` | No auth required (local dev) |
| Unset | Unset | **Fail-closed** — API returns 503 |

For personal use on your LAN, `BELLMARK_DEV_MODE=true` is fine. For anything internet-facing, set `BELLMARK_API_KEY`.

## Changing the Port

Default is 8000. To change:

```bash
# In .env:
BACKEND_PORT=9000
```

Then access at `http://localhost:9000`.

## Data & Backups

SQLite database is stored at `/app/data/bellmark.db` inside the container.

**Named volume (default):**
```yaml
volumes:
  - bellmark-data:/app/data
```

**Bind mount (recommended for NAS/backup tools):**
```yaml
volumes:
  - ./data:/app/data
```

Bind mounts make the database visible to host backup tools (Synology Hyper Backup, rsync, etc.).

**Backup:**
```bash
# Stop the container first to avoid corruption
docker compose stop
cp data/bellmark.db data/bellmark.db.backup
docker compose start
```

## Upgrading

```bash
docker compose pull        # Pull the latest image
docker compose up -d       # Restart with new version
```

Database migrations run automatically on startup. Your data is preserved.

If you built from source instead of using the published image:

```bash
git pull
docker compose up --build -d
```

## Reverse Proxy (HTTPS)

BeLLMark serves HTTP. For HTTPS, put it behind a reverse proxy.

**Caddy (simplest):**
```
bellmark.example.com {
    reverse_proxy localhost:8000
}
```

**Nginx:**
```nginx
server {
    listen 443 ssl;
    server_name bellmark.example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

The `Upgrade`/`Connection` headers are required for WebSocket support (live progress).

When using a reverse proxy, set `ALLOWED_ORIGINS` to your domain:
```bash
ALLOWED_ORIGINS=https://bellmark.example.com
```

## Platform Notes

### Synology DSM 7.2+
- Use `docker-compose` (v1, hyphenated) — `docker compose` (v2) may not be available
- Git is at `/volume1/@appstore/Git/bin/git` — add to PATH or use the full path
- Use a bind mount for Hyper Backup compatibility

### Unraid
- Install via Community Apps or manual Docker template
- Map `/app/data` to a share for backup visibility

### TrueNAS SCALE
- Deploy as a custom app with the Docker Compose file
- Map the data volume to a dataset

## Building from Source

If you prefer not to use the published image:

```bash
git clone https://github.com/Context-Management/BeLLMark.git
cd BeLLMark
cp .env.example .env
# Edit .env — set BELLMARK_SECRET_KEY and provider keys
docker compose up --build -d
```

Build takes 2-5 minutes depending on your hardware (Python deps + Node.js frontend build).

## Healthcheck

The Docker Compose file includes a healthcheck hitting `/api/health/live`. Check status:

```bash
docker compose ps    # Shows health status
docker inspect --format='{{.State.Health.Status}}' bellmark-bellmark-1
```
