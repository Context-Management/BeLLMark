#!/bin/bash
# start.sh - Start BeLLMark in development mode

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# --- Prerequisite checks ---

check_command() {
    if ! command -v "$1" &>/dev/null; then
        echo -e "${RED}Error: $1 is not installed.${NC}"
        echo "$2"
        exit 1
    fi
}

check_version() {
    local current="$1" minimum="$2" name="$3"
    if [ "$(printf '%s\n' "$minimum" "$current" | sort -V | head -n1)" != "$minimum" ]; then
        echo -e "${RED}Error: $name $current is below minimum $minimum${NC}"
        exit 1
    fi
}

# Find a suitable Python (try versioned binaries first, then generic)
PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" &>/dev/null; then
        ver=$("$candidate" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        if [ "$(printf '%s\n' "3.11" "$ver" | sort -V | head -n1)" = "3.11" ]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo -e "${RED}Error: Python 3.11+ not found.${NC}"
    echo "Install Python 3.11+ from https://python.org"
    echo "Checked: python3.13, python3.12, python3.11, python3"
    exit 1
fi

PYTHON_VERSION=$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "Using ${GREEN}$PYTHON${NC} ($PYTHON_VERSION)"

check_command node "Install Node.js 18+ from https://nodejs.org"
check_command npm "npm should come with Node.js — reinstall Node from https://nodejs.org"

NODE_VERSION=$(node -v | sed 's/^v//' | cut -d. -f1-2)
check_version "$NODE_VERSION" "18.0" "Node.js"

# --- Load environment ---

if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

BACKEND_HOST=${BACKEND_HOST:-127.0.0.1}
BACKEND_PORT=${BACKEND_PORT:-8000}
FRONTEND_PORT=${FRONTEND_PORT:-5173}

echo -e "${BLUE}Starting BeLLMark (dev mode)...${NC}"

# --- Bootstrap backend ---

cd backend
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}Creating Python virtual environment...${NC}"
    "$PYTHON" -m venv .venv
    source .venv/bin/activate
    echo -e "${YELLOW}Installing Python dependencies...${NC}"
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi
cd ..

# --- Bootstrap frontend ---

if [ ! -d "frontend/node_modules" ]; then
    echo -e "${YELLOW}Installing frontend dependencies...${NC}"
    cd frontend
    npm install
    cd ..
fi

# --- Start services ---

echo "Starting backend..."
cd backend
uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" --reload &
BACKEND_PID=$!
cd ..

sleep 2

echo "Starting frontend..."
cd frontend
npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" &
FRONTEND_PID=$!
cd ..

echo ""
echo -e "${GREEN}BeLLMark started!${NC}"
echo -e "  Frontend: ${BLUE}http://localhost:${FRONTEND_PORT}${NC}"
echo -e "  Backend:  ${BLUE}http://localhost:${BACKEND_PORT}${NC}"
echo -e "  API Docs: ${BLUE}http://localhost:${BACKEND_PORT}/docs${NC}"
echo ""
echo "Press Ctrl+C to stop"

# Handle shutdown
cleanup() {
    echo ""
    echo "Shutting down..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

wait
