# CDN Monitoring System

A distributed monitoring app with an agent that collects TCP connection counts and sends them to a FastAPI server. The server stores metrics in SQLite and exposes dashboard + APIs.

## Run
```bash
cp .env.example .env
docker compose up --build
```

Server: http://localhost:18443
