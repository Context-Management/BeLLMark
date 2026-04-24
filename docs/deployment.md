# BeLLMark Deployment Guide

> [!WARNING]
> **Do not expose BeLLMark to the public internet.**
> v1 has no built-in user accounts or RBAC. Secure access using
> your infrastructure (VPN, reverse proxy, firewall).

## Supported Deployment Topologies

### 1. Local-Only (Default)

Binds to `127.0.0.1`. Access from the same machine only. No network exposure.

```bash
# Default — no configuration needed
./start.sh
# Backend binds to 127.0.0.1:8000
# Frontend at http://localhost:5173
```

**Security:** No network attack surface. Suitable for personal evaluation.

### 2. Behind VPN

Bind to `0.0.0.0` with `BELLMARK_API_KEY` set. Access via corporate VPN.

```bash
# .env
BACKEND_HOST=0.0.0.0
BELLMARK_API_KEY=your-secret-key-here
```

**Security:** VPN provides network-level access control. API key adds application-level authentication.

### 3. Behind Reverse Proxy with Auth

Nginx/Caddy with authentication. BeLLMark binds to localhost; proxy handles TLS and auth.

```nginx
# Example Nginx configuration
server {
    listen 443 ssl;
    server_name bellmark.internal.company.com;

    ssl_certificate /etc/ssl/certs/bellmark.pem;
    ssl_certificate_key /etc/ssl/private/bellmark.key;

    # Basic auth or SSO
    auth_basic "BeLLMark";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

**Security:** TLS encryption + authentication at the proxy layer. WebSocket upgrade headers required for live progress.

### 4. Private Subnet with Firewall

Bind to LAN IP with `BELLMARK_API_KEY`. Firewall restricts access to known IPs.

```bash
# .env
BACKEND_HOST=0.0.0.0
BELLMARK_API_KEY=your-secret-key-here

# Firewall rules (example: ufw)
sudo ufw allow from 192.168.1.0/24 to any port 8000
sudo ufw deny 8000
```

**Security:** Network firewall + API key. Suitable for team evaluation on a private network.

## 5. Docker Compose

Build the image and start with Docker Compose. Data persists in a named volume.

```bash
cp .env.example .env
# Edit .env — set BELLMARK_SECRET_KEY (required) and API keys

docker compose up -d --build
# Or on older Docker / Synology NAS:
docker-compose up -d --build
```

Verify:
```bash
curl http://localhost:8000/health
# {"status":"ok","version":"1.0.0"}
```

The container binds to `0.0.0.0` inside Docker, but port mapping controls external access. Always set `BELLMARK_API_KEY` when exposing the port beyond localhost.

To rebuild after a code update:
```bash
docker compose up -d --build
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKEND_HOST` | `127.0.0.1` | Bind address (used by `start.sh`) |
| `BACKEND_PORT` | `8000` | Backend port |
| `FRONTEND_PORT` | `5173` | Frontend dev port (dev mode only) |
| `BELLMARK_API_KEY` | _(unset)_ | API key for authentication (required for non-localhost) |
| `BELLMARK_SECRET_KEY` | _(required)_ | Encryption key for stored API keys |
| `BELLMARK_DB_PATH` | `backend/bellmark.db` | Database file path (set automatically in Docker to `/app/data/bellmark.db`) |
| `ALLOWED_ORIGINS` | `localhost:5173,8000,3000` | CORS allowed origins (comma-separated) |
