from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
import os, sqlite3, time

DB = '/app/data/metrics.db'
os.makedirs('/app/data', exist_ok=True)
conn = sqlite3.connect(DB, check_same_thread=False)
conn.execute("""
CREATE TABLE IF NOT EXISTS metrics (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 ts INTEGER NOT NULL,
 cdn_name TEXT NOT NULL,
 host TEXT NOT NULL,
 target_port INTEGER NOT NULL,
 connection_count INTEGER NOT NULL
)
""")
conn.commit()
TOKEN = os.getenv('INGEST_TOKEN', 'change-me')
app = FastAPI(title='CDN Monitoring System')

class MetricIn(BaseModel):
    cdn_name: str
    host: str
    target_port: int
    connection_count: int
    ts: Optional[int] = None

@app.get('/', response_class=HTMLResponse)
def dashboard():
    return """<!doctype html><html><head><title>CDN Monitor</title>
    <style>body{font-family:Arial;background:#081018;color:#d8f7ff;padding:20px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #1f3b4d;padding:8px}a{color:#7fe8ff}</style>
    </head><body><h1>CDN Monitoring System</h1><p>Endpoints: <a href='/api/latest'>/api/latest</a></p>
    <div id='app'></div><script>
    async function load(){const r=await fetch('/api/latest');const d=await r.json();
    let html='<table><tr><th>CDN</th><th>Host</th><th>Port</th><th>Connections</th><th>Timestamp</th></tr>';
    for(const x of d.items){html+=`<tr><td>${x.cdn_name}</td><td>${x.host}</td><td>${x.target_port}</td><td>${x.connection_count}</td><td>${new Date(x.ts*1000).toLocaleString()}</td></tr>`}
    html+='</table>'; document.getElementById('app').innerHTML=html;}
    load(); setInterval(load,5000);
    </script></body></html>"""

@app.post('/api/ingest')
def ingest(metric: MetricIn, x_agent_token: Optional[str] = Header(None)):
    if x_agent_token != TOKEN:
        raise HTTPException(status_code=401, detail='invalid token')
    ts = metric.ts or int(time.time())
    conn.execute(
        'INSERT INTO metrics(ts, cdn_name, host, target_port, connection_count) VALUES (?, ?, ?, ?, ?)',
        (ts, metric.cdn_name, metric.host, metric.target_port, metric.connection_count)
    )
    conn.commit()
    return {'status': 'ok', 'ts': ts}

@app.get('/api/latest')
def latest():
    rows = conn.execute("""
    SELECT m1.ts, m1.cdn_name, m1.host, m1.target_port, m1.connection_count
    FROM metrics m1
    JOIN (
      SELECT cdn_name, MAX(ts) AS max_ts FROM metrics GROUP BY cdn_name
    ) m2 ON m1.cdn_name = m2.cdn_name AND m1.ts = m2.max_ts
    ORDER BY m1.cdn_name
    """).fetchall()
    return {'items': [
        {'ts': r[0], 'cdn_name': r[1], 'host': r[2], 'target_port': r[3], 'connection_count': r[4]}
        for r in rows
    ]}

@app.get('/api/history')
def history(cdn_name: str, minutes: int = 60):
    since = int(time.time()) - minutes * 60
    rows = conn.execute(
        'SELECT ts, connection_count FROM metrics WHERE cdn_name=? AND ts>=? ORDER BY ts',
        (cdn_name, since)
    ).fetchall()
    return {'cdn_name': cdn_name, 'points': [{'ts': r[0], 'connection_count': r[1]} for r in rows]}
