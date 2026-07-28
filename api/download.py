"""
Vercel Serverless Function - Video Downloader
Platform detection: auto-detect TikTok, YouTube, Instagram, Facebook, etc.
"""
from http.server import BaseHTTPRequestHandler
import urllib.request
import urllib.error
import json
import re
import os
import time
from urllib.parse import urlparse, unquote
from collections import defaultdict

# ─── Security Config ──────────────────────────────────────────────

RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = 10
rate_limit_store = defaultdict(list)

BLOCKED_DOMAINS = [
    'localhost', '127.0.0.1', '0.0.0.0',
    'internal', 'admin', 'api.internal',
    '.local', '.localhost',
]

ALLOWED_SCHEMES = ['http', 'https']
MAX_URL_LENGTH = 2048

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36'


# ─── Security Functions ──────────────────────────────────────────

def get_client_ip(headers):
    forwarded = headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    real_ip = headers.get('X-Real-IP')
    if real_ip:
        return real_ip
    return 'unknown'


def check_rate_limit(client_ip):
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    rate_limit_store[client_ip] = [
        t for t in rate_limit_store[client_ip] if t > window_start
    ]
    if len(rate_limit_store[client_ip]) >= RATE_LIMIT_MAX:
        return False
    rate_limit_store[client_ip].append(now)
    return True


def sanitize_url(url):
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
    domain = parsed.netloc.lower()
    for blocked in BLOCKED_DOMAINS:
        if blocked in domain:
            return None, "URL tidak diizinkan"
    ip_match = re.match(r'^(\d{1,3}\.){3}\d{1,3}$', parsed.netloc.split(':')[0])
    if ip_match:
        return None, "IP address tidak diizinkan"
    return url, None


def log_request(client_ip, url, status, error=None):
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    msg = f"[{timestamp}] {client_ip} | {url[:60]} | {status}"
    if error:
        msg += f" | {error}"
    print(msg)


# ─── Platform Detection ──────────────────────────────────────────

def detect_platform(url):
    domain = urlparse(url).netloc.lower().replace('www.', '')
    path = urlparse(url).path.lower()

    if any(path.endswith(ext) for ext in ['.mp4', '.webm', '.avi', '.mov', '.mkv', '.flv', '.m3u8', '.ts']):
        return 'direct'

    if 'tiktok.com' in domain:
        return 'tiktok'

    if domain in ('youtube.com', 'youtu.be', 'm.youtube.com'):
        return 'youtube'

    if 'instagram.com' in domain:
        return 'instagram'

    if domain in ('facebook.com', 'fb.watch', 'm.facebook.com'):
        return 'facebook'

    if domain in ('twitter.com', 'x.com'):
        return 'twitter'

    if domain in ('vimeo.com',):
        return 'vimeo'

    if domain in ('dailymotion.com', 'dai.ly'):
        return 'dailymotion'

    if 'vdy.to' in domain or 'vidio.com' in domain:
        return 'protected'

    if 'doodstream.com' in domain or 'streamtape.com' in domain:
        return 'protected'

    return 'unknown'


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


# ─── Platform Handlers ───────────────────────────────────────────

def handle_youtube(url):
    """Extract direct video URL from YouTube via yt-dlp -g flag."""
    import subprocess

    cmd = [
        'python', '-m', 'yt_dlp',
        '--no-check-certificates',
        '-g', '-f', 'best[ext=mp4]/best[height<=720]/best',
        url,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    if result.returncode != 0 or not result.stdout.strip():
        err = result.stderr.strip().split('\n')[-1] if result.stderr else 'yt-dlp gagal'
        raise Exception(f"YouTube: {err}")

    video_url = result.stdout.strip().split('\n')[0]
    parsed = urlparse(video_url)
    filename = 'youtube_video.mp4'

    return video_url, filename, url


def handle_tiktok(url):
    """Download TikTok via tikwm.com API."""
    import requests as req_lib

    r = req_lib.post(
        'https://www.tikwm.com/api/',
        data={'url': url, 'count': 12, 'cursor': 0},
        headers={'User-Agent': UA},
        timeout=30,
    )
    if r.status_code != 200:
        raise Exception(f"tikwm API error: HTTP {r.status_code}")

    data = r.json()
    if data.get('code') != 0:
        raise Exception(f"tikwm error: {data.get('msg', 'unknown')}")

    video_data = data.get('data', {})
    video_url = video_data.get('play') or video_data.get('wmplay')
    title = video_data.get('title', 'tiktok_video')

    if not video_url:
        raise Exception("Video URL tidak ditemukan dari tikwm")

    filename = sanitize_filename(title) + '.mp4'
    return video_url, filename, 'https://www.tiktok.com/'


def handle_protected(url):
    """Download from vdy.to / vidio.com."""
    import requests as req_lib

    headers = {'User-Agent': UA}

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
                return u, get_filename_from_url(u), stream_url

    raise Exception("URL video tidak ditemukan")


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

        if not check_rate_limit(client_ip):
            log_request(client_ip, '', 429, 'rate limit exceeded')
            self.send_json(429, {'error': 'Terlalu banyak request. Coba lagi nanti.'})
            return

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

        url, error = sanitize_url(url)
        if error:
            log_request(client_ip, url or '', 400, error)
            self.send_json(400, {'error': error})
            return

        platform = detect_platform(url)
        log_request(client_ip, url, 200, platform)

        try:
            if platform == 'direct':
                self.proxy_download(url, get_filename_from_url(url), url)

            elif platform == 'tiktok':
                video_url, filename, referer = handle_tiktok(url)
                self.proxy_download(video_url, filename, referer)

            elif platform == 'youtube':
                video_url, filename, referer = handle_youtube(url)
                self.proxy_download(video_url, filename, referer)

            elif platform == 'protected':
                video_url, filename, referer = handle_protected(url)
                self.proxy_download(video_url, filename, referer)

            elif platform in ('instagram', 'facebook', 'twitter', 'vimeo', 'dailymotion'):
                try:
                    video_url, filename, referer = handle_youtube(url)
                    self.proxy_download(video_url, filename, referer)
                except:
                    try:
                        self.download_ytdlp(url, get_filename_from_url(url))
                    except:
                        hint = {
                            'instagram': 'Instagram butuh login. Coba paste direct URL video (bukan link postingan).',
                            'facebook': 'Facebook butuh login. Coba pakai link watch/v/ langsung.',
                            'twitter': 'Twitter/X butuh login untuk download video.',
                            'vimeo': 'Gagal extract dari Vimeo.',
                            'dailymotion': 'Gagal extract dari DailyMotion.',
                        }.get(platform, f'Gagal download dari {platform}')
                        raise Exception(hint)

            else:
                try:
                    video_url, filename, referer = handle_protected(url)
                    self.proxy_download(video_url, filename, referer)
                except:
                    try:
                        video_url, filename, referer = handle_youtube(url)
                        self.proxy_download(video_url, filename, referer)
                    except:
                        self.download_ytdlp(url, get_filename_from_url(url))

        except Exception as e:
            log_request(client_ip, url, 500, str(e))
            self.send_json(500, {'error': str(e)})

    def proxy_download(self, video_url, filename, referer):
        import requests as req_lib

        headers = {'User-Agent': UA}
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
