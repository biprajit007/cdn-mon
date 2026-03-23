import os, time, socket, subprocess, requests

def detect_host_ip():
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return '127.0.0.1'

def count_connections(port: int) -> int:
    try:
        out = subprocess.check_output(['sh', '-lc', f"ss -tan '( sport = :{port} or dport = :{port} )' | tail -n +2 | wc -l"], text=True)
        return int(out.strip())
    except Exception:
        return 0

CDN_NAME = os.getenv('CDN_NAME', 'cdn1')
TARGET_PORT = int(os.getenv('TARGET_PORT', '443'))
INTERVAL_SECONDS = int(os.getenv('INTERVAL_SECONDS', '10'))
SERVER_ENDPOINT = os.getenv('SERVER_ENDPOINT', 'http://server:18443/api/ingest')
TOKEN = os.getenv('INGEST_TOKEN', 'change-me')
HOST = os.getenv('AGENT_HOST', detect_host_ip())

while True:
    payload = {
        'cdn_name': CDN_NAME,
        'host': HOST,
        'target_port': TARGET_PORT,
        'connection_count': count_connections(TARGET_PORT),
    }
    try:
        resp = requests.post(SERVER_ENDPOINT, json=payload, headers={'X-Agent-Token': TOKEN}, timeout=10)
        print(resp.status_code, resp.text)
    except Exception as e:
        print('send failed:', e)
    time.sleep(INTERVAL_SECONDS)
