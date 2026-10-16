FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8000 DB_PATH=/app/trades.db
EXPOSE 8000
CMD ["sh", "-c", "python -m backend.db && uvicorn backend.app:app --host 0.0.0.0 --port $PORT"]
