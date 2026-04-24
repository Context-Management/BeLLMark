# Stage 1: Build frontend
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
COPY VERSION /app/VERSION
RUN npm run build

# Stage 2: Runtime
FROM python:3.12-slim AS runtime
WORKDIR /app

# Install system deps for SQLite and python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl \
    libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 libcairo2 libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps (pinned for reproducibility)
COPY backend/requirements-lock.txt ./backend/requirements-lock.txt
RUN pip install --no-cache-dir -r backend/requirements-lock.txt

# Copy backend
COPY backend/ ./backend/

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Copy root files needed at runtime
COPY VERSION ./
COPY .env.example ./.env.example

# Create data directory for SQLite
RUN mkdir -p /app/data

EXPOSE 8000

# Default env vars
ENV BELLMARK_HOST=0.0.0.0
ENV BACKEND_PORT=8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "backend"]
