#!/bin/bash
# Start PaperAlpha live: app on :8000 + free public tunnel
cd ~/workspace/ai-paper-trader
rm -f nohup.out
nohup .venv/bin/uvicorn backend.app:app --host 127.0.0.1 --port 8000 > /tmp/pa_app.log 2>&1 &
echo "app started"
sleep 4
nohup cloudflared tunnel --url http://127.0.0.1:8000 > /tmp/pa_tunnel.log 2>&1 &
echo "tunnel started"
