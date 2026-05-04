import os, time, socket, subprocess, requests, logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def detect_host_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        logger.warning('Failed to detect host IP, using localhost')
        return 'localhost'

def count_connections(port: int) -> int:
    try:
        out = subprocess.check_output(
            ['ss', '-tan', f'sport = :{port} or dport = :{port}'],
            text=True, stderr=subprocess.DEVNULL
        )
        return max(0, len(out.strip().split('\n')) - 1)
    except Exception as e:
        logger.error(f'Failed to count connections on port {port}: {e}')
        return 0

CDN_NAME = os.getenv('CDN_NAME', 'cdn1')
TARGET_PORT = int(os.getenv('TARGET_PORT', '443'))
INTERVAL_SECONDS = int(os.getenv('INTERVAL_SECONDS', '10'))
SERVER_ENDPOINT = os.getenv('SERVER_ENDPOINT', 'http://server:18443/api/ingest')
TOKEN = os.getenv('INGEST_TOKEN', 'change-me')
HOST = os.getenv('AGENT_HOST', detect_host_ip())

logger.info(f'Starting agent: CDN={CDN_NAME}, Port={TARGET_PORT}, Host={HOST}')

retry_count = 0
max_retries = 5

while True:
    payload = {
        'cdn_name': CDN_NAME,
        'host': HOST,
        'target_port': TARGET_PORT,
        'connection_count': count_connections(TARGET_PORT),
    }
    try:
        resp = requests.post(
            SERVER_ENDPOINT,
            json=payload,
            headers={'X-Agent-Token': TOKEN},
            timeout=10
        )
        if resp.status_code == 200:
            logger.info(f'Metrics sent: {payload["connection_count"]} connections')
            retry_count = 0
        else:
            logger.error(f'Server error {resp.status_code}: {resp.text}')
            retry_count += 1
    except Exception as e:
        logger.error(f'Failed to send metrics: {e}')
        retry_count += 1

    if retry_count > max_retries:
        logger.error(f'Max retries exceeded, exiting')
        break

    time.sleep(INTERVAL_SECONDS)
