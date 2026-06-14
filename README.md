# cdn-mon

CDN monitoring portal — real-time dashboard for tracking connection counts and bandwidth across CDN nodes.

## Stack

- **Backend:** FastAPI + Uvicorn, SQLite (WAL mode)
- **Frontend:** Inline HTML/JS, Chart.js, Leaflet maps
- **Auth:** JWT session cookies, bcrypt passwords
- **Proxy:** nginx:1.25-alpine (handles HTTPS + agent ingest port)

## Features

- Real-time connection count and TX/RX bandwidth per CDN node
- Connection graph, bandwidth graph, peak load gauge
- World/Bangladesh map with CDN node pins
- Historical trends (24h / 7d / 30d)
- CDN management page (add/remove nodes, map placement)
- Multi-user login with JWT sessions

## Quick Start

```bash
git clone https://github.com/biprajit007/cdn-mon.git
cd cdn-mon

# 1. Configure environment
cp .env.example .env
nano .env   # set JWT_SECRET, LEGACY_API_KEY, INGEST_TOKEN

# 2. Place SSL certs
cp /path/to/cert.pem ssl/
cp /path/to/key.pem  ssl/

# 3. Deploy
docker compose up -d
```

Portal: `https://<your-domain>:18443`  
Default login: `admin` / `cdn-monitor-2026!`

## Ports

| Port | Purpose |
|------|---------|
| 18443 | HTTPS portal |
| 18080 | Agent metric ingest (HTTP) |
| 18880 | HTTP → HTTPS redirect |

## Agent Integration

Metrics are pushed by **[rocks-cdn](https://github.com/biprajit007/rocks-cdn)** agents running on each CDN node.

Agent sends `POST /api/metrics` with:
```json
{
  "server_id": "cdn1",
  "connection_count": 1234,
  "tx_bps": 500000000,
  "rx_bps": 100000000
}
```
Header: `X-API-Key: <LEGACY_API_KEY>`

## Map Configuration

Edit `data/cdn_map.json` (created automatically, use management page or edit directly):
```json
{
  "cdn1": { "place_name": "Dhaka",      "area_name": "Mirpur" },
  "cdn2": { "place_name": "Chattogram", "area_name": "Agrabad" }
}
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/metrics` | Agent ingest (legacy, X-API-Key) |
| `POST /api/ingest` | Agent ingest (new, X-Agent-Token) |
| `GET /api/latest` | Latest metrics per CDN |
| `GET /api/series?range=24h` | Connection time series |
| `GET /api/bandwidth?minutes=30` | TX/RX bandwidth series |
| `GET /api/map-config` | CDN map markers |
| `GET /api/history` | Historical data |
