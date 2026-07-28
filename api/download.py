"""
Vercel Serverless Function - Video Downloader
Support: direct URL + situs protected (vdy.to, dll)
"""
from http.server import BaseHTTPRequestHandler
import urllib.request
import urllib.error
import json
import re
import os
from urllib.parse import urlparse, unquote


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


def extract_vdy_url(url):
    """Extract direct video URL dari vdy.to"""
    import requests as req_lib

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    # Step 1: Fetch halaman utama
    r = req_lib.get(url, headers=headers, timeout=15)
    if r.status_code != 200:
        raise Exception(f"Gagal fetch: HTTP {r.status_code}")

    id_match = re.search(r"var iframeId\s*=\s*['\"]([^'\"]+)['\"]", r.text)
    token_match = re.search(r"var embedToken\s*=\s*['\"]([^'\"]+)['\"]", r.text)
    if not id_match or not token_match:
        raise Exception("iframeId/embedToken tidak ditemukan")

    iframe_id = id_match.group(1)
    token = token_match.group(1)

    # Step 2: Fetch halaman player
    domain = urlparse(url).netloc
    iframe_url = f"https://{domain}/ip129jk?id={iframe_id}&t={token}"
    r2 = req_lib.get(iframe_url, headers={**headers, 'Referer': url}, timeout=15)

    # Step 3: Cari stream.php URL
    prefetch = re.search(r'prefetch.*?href=["\']([^"\']+)["\']', r2.text)
    if not prefetch:
        raise Exception("Stream URL tidak ditemukan")

    stream_url = prefetch.group(1).replace('&amp;', '&')
    r3 = req_lib.get(stream_url, headers={**headers, 'Referer': iframe_url}, timeout=15)

    # Cari URL video
    all_urls = re.findall(r'https?://[^\s"\'<>]+', r3.text)
    for u in all_urls:
        if any(x in u for x in ['mp4', 'overfetch', 'cdn']):
            if 'google' not in u and 'jquery' not in u and 'stream.php' not in u:
                return u, stream_url

    raise Exception("URL video tidak ditemukan")


def extract_video_url(url):
    """Extract direct video URL dari situs protected"""
    domain = urlparse(url).netloc.lower()
    if 'vdy.to' in domain:
        return extract_vdy_url(url)
    raise Exception(f"Tidak bisa extract dari {domain}")


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
        url = None

        # Ambil URL dari query string
        if '?' in self.path:
            query = self.path.split('?', 1)[1]
            for param in query.split('&'):
                if param.startswith('url='):
                    url = unquote(param[4:])
                    break

        # Atau dari body POST
        if not url:
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length)
                data = json.loads(body)
                url = data.get('url')
            except:
                pass

        if not url:
            self.send_json(400, {'error': 'URL tidak ditemukan'})
            return

        try:
            parsed = urlparse(url)
            if not parsed.scheme in ('http', 'https'):
                self.send_json(400, {'error': 'URL harus http atau https'})
                return
        except:
            self.send_json(400, {'error': 'URL tidak valid'})
            return

        filename = get_filename_from_url(url)
        referer = None

        try:
            # Direct URL - langsung download
            if is_direct_url(url):
                video_url = url
                referer = url
            else:
                # Protected site - extract dulu
                video_url, referer = extract_video_url(url)
                filename = get_filename_from_url(video_url)

            # Download video
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

            # Stream video ke client
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

        except Exception as e:
            self.send_json(500, {'error': str(e)})

    def send_json(self, code, data):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
