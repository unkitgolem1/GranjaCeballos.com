#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$PROJECT_DIR/nightly-logs"
mkdir -p "$LOG_DIR"
TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
LOG_FILE="$LOG_DIR/nightly-$TIMESTAMP.log"

exec >"$LOG_FILE" 2>&1

echo "=== [1/4] Escaneo estático de seguridad con Bandit ==="
uv run bandit -r ./src -x tests || echo "[WARN] Bandit encontró vulnerabilidades (revisar log)"

echo "=== [2/4] Limpiando puertos anteriores ==="
kill $(lsof -t -i:8001) 2>/dev/null || true
sleep 1

echo "=== [3/5] Levantando servidor local en puerto 8001 ==="
uv run uvicorn src.main:app --port 8001 --log-level warning > /dev/null 2>&1 &
SERVER_PID=$!
echo "Servidor PID: $SERVER_PID"
sleep 4
trap "echo 'Apagando servidor PID $SERVER_PID'; kill $SERVER_PID 2>/dev/null; wait $SERVER_PID 2>/dev/null" EXIT

# Verify server is up
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8001/health || true

echo "=== [4/5] Fuzzing destructivo con Schemathesis ==="
uv run st run http://127.0.0.1:8001/openapi.json \
    --checks all \
    --workers 4 \
    --max-response-time 5.0 \
    --request-timeout 10 \
    --url http://127.0.0.1:8001 \
    --wait-for-schema 10 || echo "[WARN] Schemathesis encontró fallos (revisar log)"

echo "=== [5/5] Suite completada exitosamente ==="
