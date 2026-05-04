from fastapi import FastAPI, Header, HTTPException, Cookie, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from typing import Optional
import os, sqlite3, time, html, logging
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_cdn_ts ON metrics(cdn_name, ts)")
conn.execute("""
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 username TEXT UNIQUE NOT NULL,
 hashed_password TEXT NOT NULL,
 created_at INTEGER NOT NULL
)
""")
conn.commit()

TOKEN = os.getenv('INGEST_TOKEN', 'change-me')
JWT_SECRET = os.getenv('JWT_SECRET', 'change-me-in-production')
JWT_ALGORITHM = 'HS256'
SESSION_HOURS = int(os.getenv('SESSION_HOURS', '24'))
RETENTION_DAYS = int(os.getenv('RETENTION_DAYS', '30'))
BOOTSTRAP_ADMIN_USERNAME = os.getenv('BOOTSTRAP_ADMIN_USERNAME', 'admin')
BOOTSTRAP_ADMIN_PASSWORD = os.getenv('BOOTSTRAP_ADMIN_PASSWORD', 'cdn-monitor-2026!')
AUTO_BOOTSTRAP_ADMIN = os.getenv('AUTO_BOOTSTRAP_ADMIN', 'true').lower() in ('1', 'true', 'yes', 'on')

pwd_context = CryptContext(schemes=['argon2'], deprecated='auto')
app = FastAPI(title='CDN Monitoring System')

class MetricIn(BaseModel):
    cdn_name: str
    host: str
    target_port: int
    connection_count: int
    ts: Optional[int] = None

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def hash_password(password):
    return pwd_context.hash(password)

def create_token(username: str, expires_hours: int = SESSION_HOURS):
    exp = datetime.utcnow() + timedelta(hours=expires_hours)
    return jwt.encode({'sub': username, 'exp': exp}, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_token(token: Optional[str] = Cookie(None)) -> str:
    if not token:
        raise HTTPException(status_code=401, detail='Not authenticated')
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username = payload.get('sub')
        if not username:
            raise HTTPException(status_code=401, detail='Invalid token')
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail='Invalid token')

def username_from_token(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get('sub')
    except JWTError:
        return None

def cleanup_old_metrics():
    cutoff = int(time.time()) - (RETENTION_DAYS * 86400)
    conn.execute('DELETE FROM metrics WHERE ts < ?', (cutoff,))
    conn.commit()
    logger.info(f'Cleaned up metrics older than {RETENTION_DAYS} days')

def bootstrap_admin_if_needed():
    if not AUTO_BOOTSTRAP_ADMIN:
        return
    row = conn.execute('SELECT COUNT(*) FROM users').fetchone()
    if row and row[0] > 0:
        return
    hashed = hash_password(BOOTSTRAP_ADMIN_PASSWORD)
    conn.execute(
        'INSERT OR REPLACE INTO users(username, hashed_password, created_at) VALUES (?, ?, ?)',
        (BOOTSTRAP_ADMIN_USERNAME, hashed, int(time.time()))
    )
    conn.commit()
    logger.warning('Bootstrapped default admin user %s', BOOTSTRAP_ADMIN_USERNAME)


@app.on_event('startup')
def startup():
    bootstrap_admin_if_needed()

@app.get('/login', response_class=HTMLResponse)
def login_page():
    bootstrap_hint = ''
    if AUTO_BOOTSTRAP_ADMIN:
        bootstrap_hint = f"<p style='font-size:12px;opacity:.8'>First login: {html.escape(BOOTSTRAP_ADMIN_USERNAME)} / {html.escape(BOOTSTRAP_ADMIN_PASSWORD)}</p>"
    return """<!doctype html><html><head><title>CDN Monitor Login</title>
    <style>body{{font-family:Arial;background:#081018;color:#d8f7ff;padding:20px;display:flex;justify-content:center;align-items:center;height:100vh;margin:0}}
    .login-box{{border:1px solid #1f3b4d;padding:30px;border-radius:5px;width:300px}}input{{width:100%;padding:10px;margin:10px 0;background:#0a1520;border:1px solid #1f3b4d;color:#d8f7ff;box-sizing:border-box}}
    button{{width:100%;padding:10px;margin-top:10px;background:#1f3b4d;color:#7fe8ff;border:1px solid #7fe8ff;cursor:pointer}}button:hover{{background:#2a4a5d}}
    .error{{color:#ff6b6b;margin-bottom:10px}}</style>
    </head><body><div class='login-box'><h1>CDN Monitor</h1>
    <form method='post' action='/api/login'><input type='text' name='username' placeholder='Username' required>
    <input type='password' name='password' placeholder='Password' required><button type='submit'>Login</button></form>{bootstrap_hint}</div></body></html>""".format(bootstrap_hint=bootstrap_hint)

@app.post('/api/login')
def api_login(username: str = Form(...), password: str = Form(...)):
    user = conn.execute('SELECT hashed_password FROM users WHERE username=?', (username,)).fetchone()
    if not user or not verify_password(password, user[0]):
        logger.warning(f'Failed login attempt for user: {username}')
        raise HTTPException(status_code=401, detail='Invalid credentials')
    token = create_token(username)
    response = RedirectResponse(url='/', status_code=303)
    response.set_cookie(key='token', value=token, httponly=True, max_age=SESSION_HOURS*3600)
    logger.info(f'User logged in: {username}')
    return response

@app.get('/logout')
def logout():
    response = RedirectResponse(url='/login', status_code=303)
    response.delete_cookie('token')
    logger.info('User logged out')
    return response

@app.get('/', response_class=HTMLResponse)
def dashboard(token: Optional[str] = Cookie(None)):
    username = username_from_token(token)
    if not username:
        return RedirectResponse(url='/login', status_code=303)
    cleanup_old_metrics()
    return f"""<!doctype html><html><head><title>CDN Monitor</title>
    <style>
    body{{font-family:Arial;background:#081018;color:#d8f7ff;padding:20px;margin:0}}
    a{{color:#7fe8ff}}
    .logout{{float:right}}
    .topbar{{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}}
    .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:18px 0}}
    .card{{background:#0a1520;border:1px solid #1f3b4d;border-radius:10px;padding:14px}}
    .card .label{{font-size:12px;opacity:.75;margin-bottom:6px}}
    .card .value{{font-size:24px;font-weight:700}}
    .panel{{background:#0a1520;border:1px solid #1f3b4d;border-radius:10px;padding:14px;margin-top:16px}}
    .panel h2{{margin:0 0 12px 0;font-size:18px}}
    table{{border-collapse:collapse;width:100%}}
    td,th{{border:1px solid #1f3b4d;padding:8px;text-align:left}}
    select{{background:#081018;color:#d8f7ff;border:1px solid #1f3b4d;padding:8px;border-radius:6px}}
    .muted{{opacity:.75}}
    .empty{{padding:16px 0;opacity:.75}}
    .chart{{width:100%;height:220px;display:block;background:#081018;border:1px solid #1f3b4d;border-radius:8px}}
    </style>
    </head><body><h1>CDN Monitoring System</h1><a href='/logout' class='logout'>Logout ({html.escape(username)})</a>
    <p class='muted'>Endpoints: <a href='/api/latest'>/api/latest</a> · <a href='/api/history?cdn_name=cdn1'>/api/history</a></p>
    <div class='grid' id='summary'></div>
    <div class='panel'>
      <h2>Trend</h2>
      <div style='display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:12px'>
        <label for='cdnSelect' class='muted'>CDN</label>
        <select id='cdnSelect'></select>
        <span id='trendMeta' class='muted'></span>
      </div>
      <svg id='trendChart' class='chart' viewBox='0 0 900 220' preserveAspectRatio='none'></svg>
      <div id='trendEmpty' class='empty' style='display:none'>No history yet for this CDN.</div>
    </div>
    <div class='panel'>
      <h2>Latest metrics</h2><div id='app'></div>
    </div>
    <script>
    const state = {{ items: [], selected: null }};
    function el(tag, attrs={{}}, text=''){{ const node=document.createElement(tag); for(const [k,v] of Object.entries(attrs)){{ if(k==='class') node.className=v; else if(k==='text') node.textContent=v; else node.setAttribute(k,v); }} if(text) node.textContent=text; return node; }}
    function renderSummary(items){{
      const totalConnections = items.reduce((sum, x) => sum + Number(x.connection_count || 0), 0);
      const lastSeen = items.length ? new Date(Math.max(...items.map(x => x.ts))*1000).toLocaleString() : 'n/a';
      const summary = document.getElementById('summary');
      summary.replaceChildren(
        el('div', {{class:'card'}}, ''),
        el('div', {{class:'card'}}, ''),
        el('div', {{class:'card'}}, '')
      );
      summary.children[0].innerHTML = '<div class="label">CDNs</div><div class="value">' + items.length + '</div>';
      summary.children[1].innerHTML = '<div class="label">Total connections</div><div class="value">' + totalConnections + '</div>';
      summary.children[2].innerHTML = '<div class="label">Last update</div><div class="value" style="font-size:16px">' + lastSeen + '</div>';
    }}
    function renderTable(items){{
      const app=document.getElementById('app');
      if(!items.length){{ app.innerHTML = '<div class="empty">No metrics yet.</div>'; return; }}
      const table=document.createElement('table');
      const head=document.createElement('tr');
      for (const title of ['CDN','Host','Port','Connections','Timestamp']){{ head.appendChild(el('th', {{text:title}})); }}
      table.appendChild(head);
      for(const x of items){{
        const tr=document.createElement('tr');
        tr.appendChild(el('td', {{text:x.cdn_name}}));
        tr.appendChild(el('td', {{text:x.host}}));
        tr.appendChild(el('td', {{text:String(x.target_port)}}));
        tr.appendChild(el('td', {{text:String(x.connection_count)}}));
        tr.appendChild(el('td', {{text:new Date(x.ts*1000).toLocaleString()}}));
        table.appendChild(tr);
      }}
      app.replaceChildren(table);
    }}
    function renderSelector(items){{
      const select = document.getElementById('cdnSelect');
      const names = [...new Set(items.map(x => x.cdn_name))];
      const current = state.selected && names.includes(state.selected) ? state.selected : names[0] || '';
      select.replaceChildren(...names.map(name => el('option', {{value:name, text:name}})));
      select.value = current;
      state.selected = current;
      select.onchange = () => {{ state.selected = select.value; loadTrend(); }};
      document.getElementById('trendMeta').textContent = current ? ('showing last 60 minutes for ' + current) : '';
    }}
    function drawBars(points){{
      const svg = document.getElementById('trendChart');
      const empty = document.getElementById('trendEmpty');
      svg.replaceChildren();
      if(!points.length){{ empty.style.display='block'; return; }}
      empty.style.display='none';
      const max = Math.max(...points.map(p => Number(p.connection_count || 0)), 1);
      const w = 900, h = 220, pad = 18;
      const barW = Math.max(8, Math.floor((w - pad*2) / points.length) - 4);
      const step = (w - pad*2) / points.length;
      points.forEach((p, i) => {{
        const val = Number(p.connection_count || 0);
        const barH = Math.max(2, Math.round((val / max) * (h - 50)));
        const x = pad + i * step;
        const y = h - 28 - barH;
        const rect = document.createElementNS('http://www.w3.org/2000/svg','rect');
        rect.setAttribute('x', x.toFixed(1));
        rect.setAttribute('y', y);
        rect.setAttribute('width', barW);
        rect.setAttribute('height', barH);
        rect.setAttribute('rx', 3);
        rect.setAttribute('fill', '#7fe8ff');
        svg.appendChild(rect);
      }});
      const axis = document.createElementNS('http://www.w3.org/2000/svg','line');
      axis.setAttribute('x1','16'); axis.setAttribute('x2','884'); axis.setAttribute('y1','192'); axis.setAttribute('y2','192');
      axis.setAttribute('stroke','#1f3b4d'); axis.setAttribute('stroke-width','1');
      svg.appendChild(axis);
      const label = document.createElementNS('http://www.w3.org/2000/svg','text');
      label.setAttribute('x','18'); label.setAttribute('y','16'); label.setAttribute('fill','#d8f7ff'); label.setAttribute('font-size','12');
      label.textContent = 'max connections: ' + max;
      svg.appendChild(label);
    }}
    async function loadTrend(){{
      if(!state.selected){{ drawBars([]); return; }}
      const r=await fetch('/api/history?cdn_name=' + encodeURIComponent(state.selected) + '&minutes=60');
      const d=await r.json();
      document.getElementById('trendMeta').textContent = 'showing last 60 minutes for ' + state.selected + ' (' + d.points.length + ' points)';
      drawBars(d.points || []);
    }}
    async function load(){{
      const r=await fetch('/api/latest');
      const d=await r.json();
      state.items = d.items || [];
      renderSummary(state.items);
      renderSelector(state.items);
      renderTable(state.items);
      await loadTrend();
    }}
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
    SELECT ts, cdn_name, host, target_port, connection_count
    FROM metrics
    WHERE (cdn_name, ts) IN (
      SELECT cdn_name, MAX(ts) FROM metrics GROUP BY cdn_name
    )
    ORDER BY cdn_name
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
