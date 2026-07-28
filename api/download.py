"""
Vercel Serverless Function - Video Downloader
Security: rate limiting, input validation, URL filtering
"""
from http.server import BaseHTTPRequestHandler
import urllib.request
import urllib.error
import json
import re
import os
import time
import hashlib
from urllib.parse import urlparse, unquote
from collections import defaultdict

# ─── Security Config ──────────────────────────────────────────────

RATE_LIMIT_WINDOW = 60  # detik
RATE_LIMIT_MAX = 10     # max request per window
rate_limit_store = defaultdict(list)

BLOCKED_DOMAINS = [
    'localhost', '127.0.0.1', '0.0.0.0',
    'internal', 'admin', 'api.internal',
    '.local', '.localhost',
]

ALLOWED_SCHEMES = ['http', 'https']

MAX_URL_LENGTH = 2048


# ─── Security Functions ──────────────────────────────────────────

def get_client_ip(headers):
    """Get real client IP from headers."""
    forwarded = headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    real_ip = headers.get('X-Real-IP')
    if real_ip:
        return real_ip
    return 'unknown'


def check_rate_limit(client_ip):
    """Check if client exceeded rate limit."""
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    
    # Clean old entries
    rate_limit_store[client_ip] = [
        t for t in rate_limit_store[client_ip] if t > window_start
    ]
    
    if len(rate_limit_store[client_ip]) >= RATE_LIMIT_MAX:
        return False
    
    rate_limit_store[client_ip].append(now)
    return True


def sanitize_url(url):
    """Validate and sanitize URL."""
    if not url or not isinstance(url, str):
        return None, "URL kosong"
    
    url = url.strip()
    
    if len(url) > MAX_URL_LENGTH:
        return None, "URL terlalu panjang"
    
    try:
        parsed = urlparse(url)
    except Exception:
        return None, "URL tidak valid"
    
    if parsed.scheme not in ALLOWED_SCHEMES:
        return None, "URL harus http atau https"
    
    if not parsed.netloc:
        return None, "URL tidak valid"
    
    # Block internal/private IPs
    domain = parsed.netloc.lower()
    for blocked in BLOCKED_DOMAINS:
        if blocked in domain:
            return None, "URL tidak diizinkan"
    
    # Block IP addresses (prevent SSRF)
    ip_match = re.match(r'^(\d{1,3}\.){3}\d{1,3}$', parsed.netloc.split(':')[0])
    if ip_match:
        return None, "IP address tidak diizinkan"
    
    return url, None


def log_request(client_ip, url, status, error=None):
    """Simple request logging."""
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    msg = f"[{timestamp}] {client_ip} | {url[:50]} | {status}"
    if error:
        msg += f" | {error}"
    print(msg)


# ─── Video Extract Functions ──────────────────────────────────────

PROTECTED_SITES = ['vdy.to', 'vidio.com', 'doodstream.com', 'streamtape.com']

YTDLP_SITES = [
    'youtube.com', 'youtu.be', 'www.youtube.com', 'm.youtube.com',
    'facebook.com', 'fb.watch', 'www.facebook.com', 'm.facebook.com',
    'instagram.com', 'www.instagram.com',
    'tiktok.com', 'www.tiktok.com', 'vm.tiktok.com',
    'twitter.com', 'x.com', 'www.twitter.com', 'www.x.com',
    'vimeo.com', 'dailymotion.com',
]


def sanitize_filename(name):
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.strip('. ')
    return name or 'video'


def get_filename_from_url(url):
    parsed = urlparse(url)
    path = unquote(parsed.path)
    name = os.path.basename(path)
    if not name or '.' not in name:
        return 'video.mp4'
    return sanitize_filename(name)


def is_direct_url(url):
    parsed = urlparse(url)
    path = parsed.path.lower()
    return any(path.endswith(ext) for ext in ['.mp4', '.webm', '.avi', '.mov', '.mkv', '.flv', '.m3u8', '.ts'])


def is_ytdlp_site(url):
    domain = urlparse(url).netloc.lower()
    return any(site in domain for site in YTDLP_SITES)


def is_protected_site(url):
    domain = urlparse(url).netloc.lower()
    return any(site in domain for site in PROTECTED_SITES)


def extract_vdy_url(url):
    import requests as req_lib
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    r = req_lib.get(url, headers=headers, timeout=15)
    if r.status_code != 200:
        raise Exception(f"Gagal fetch: HTTP {r.status_code}")

    id_match = re.search(r"var iframeId\s*=\s*['\"]([^'\"]+)['\"]", r.text)
    token_match = re.search(r"var embedToken\s*=\s*['\"]([^'\"]+)['\"]", r.text)
    if not id_match or not token_match:
        raise Exception("iframeId/embedToken tidak ditemukan")

    domain = urlparse(url).netloc
    iframe_url = f"https://{domain}/ip129jk?id={id_match.group(1)}&t={token_match.group(1)}"
    r2 = req_lib.get(iframe_url, headers={**headers, 'Referer': url}, timeout=15)

    prefetch = re.search(r'prefetch.*?href=["\']([^"\']+)["\']', r2.text)
    if not prefetch:
        raise Exception("Stream URL tidak ditemukan")

    stream_url = prefetch.group(1).replace('&amp;', '&')
    r3 = req_lib.get(stream_url, headers={**headers, 'Referer': iframe_url}, timeout=15)

    all_urls = re.findall(r'https?://[^\s"\'<>]+', r3.text)
    for u in all_urls:
        if any(x in u for x in ['mp4', 'overfetch', 'cdn']):
            if 'google' not in u and 'jquery' not in u and 'stream.php' not in u:
                return u, stream_url

    raise Exception("URL video tidak ditemukan")


def extract_video_url(url):
    domain = urlparse(url).netloc.lower()
    if 'vdy.to' in domain:
        return extract_vdy_url(url)
    raise Exception(f"Tidak bisa extract dari {domain}")


# ─── Vercel Handler ──────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        if self.path.startswith('/api/download'):
            self.handle_download()
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == '/api/download':
            self.handle_download()
        else:
            self.send_error(404)

    def handle_download(self):
        client_ip = get_client_ip(self.headers)

        # Rate limiting
        if not check_rate_limit(client_ip):
            log_request(client_ip, '', 429, 'rate limit exceeded')
            self.send_json(429, {'error': 'Terlalu banyak request. Coba lagi nanti.'})
            return

        # Extract URL
        url = None
        if '?' in self.path:
            query = self.path.split('?', 1)[1]
            for param in query.split('&'):
                if param.startswith('url='):
                    url = unquote(param[4:])
                    break

        if not url:
            try:
                length = int(self.headers.get('Content-Length', 0))
                if length > 8192:
                    self.send_json(400, {'error': 'Request terlalu besar'})
                    return
                body = self.rfile.read(length)
                data = json.loads(body)
                url = data.get('url')
            except:
                pass

        # Validate URL
        url, error = sanitize_url(url)
        if error:
            log_request(client_ip, url or '', 400, error)
            self.send_json(400, {'error': error})
            return

        filename = get_filename_from_url(url)
        referer = None

        try:
            # Direct URL
            if is_direct_url(url):
                video_url = url
                referer = url
            # Social media / big sites → yt-dlp
            elif is_ytdlp_site(url):
                log_request(client_ip, url, 200, 'yt-dlp')
                self.download_ytdlp(url, filename)
                return
            # Protected sites
            elif is_protected_site(url):
                video_url, referer = extract_video_url(url)
                filename = get_filename_from_url(video_url)
            else:
                # Try extract, fallback yt-dlp
                try:
                    video_url, referer = extract_video_url(url)
                    filename = get_filename_from_url(video_url)
                except:
                    log_request(client_ip, url, 200, 'yt-dlp fallback')
                    self.download_ytdlp(url, filename)
                    return

            # Download via proxy
            log_request(client_ip, url, 200, 'direct proxy')
            self.proxy_download(video_url, filename, referer)

        except Exception as e:
            log_request(client_ip, url, 500, str(e))
            self.send_json(500, {'error': str(e)})

    def proxy_download(self, video_url, filename, referer):
        import requests as req_lib

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        if referer:
            headers['Referer'] = referer
            parsed_ref = urlparse(referer)
            headers['Origin'] = f"{parsed_ref.scheme}://{parsed_ref.netloc}"

        resp = req_lib.get(video_url, headers=headers, stream=True, timeout=30)
        resp.raise_for_status()

        content_type = resp.headers.get('Content-Type', 'video/mp4')
        content_length = resp.headers.get('Content-Length')

        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.send_header('Access-Control-Allow-Origin', '*')
        if content_length:
            self.send_header('Content-Length', content_length)
        self.end_headers()

        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                self.wfile.write(chunk)
                self.wfile.flush()

    def download_ytdlp(self, url, filename):
        """yt-dlp download - streams progress as JSON lines."""
        import subprocess
        import tempfile

        outdir = tempfile.mkdtemp()
        outtmpl = os.path.join(outdir, '%(title)s.%(ext)s')

        self.send_response(200)
        self.send_header('Content-Type', 'application/x-ndjson')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        def send_line(data):
            self.wfile.write((json.dumps(data) + '\n').encode())
            self.wfile.flush()

        cmd = [
            'python', '-m', 'yt_dlp',
            '--no-check-certificates',
            '--progress',
            '--newline',
            '-o', outtmpl,
            url
        ]

        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1
            )

            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                send_line({'log': line})

            proc.wait()

            if proc.returncode != 0:
                send_line({'error': f'yt-dlp gagal (exit code {proc.returncode})'})
                return

            # Find downloaded file
            for f in os.listdir(outdir):
                filepath = os.path.join(outdir, f)
                send_line({'file': f, 'size': os.path.getsize(filepath)})

        except Exception as e:
            send_line({'error': str(e)})

    def send_json(self, code, data):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
