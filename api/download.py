"""
Vercel Serverless Function - Video Downloader
"""
from http.server import BaseHTTPRequestHandler
import urllib.request
import urllib.error
import json
import re
import os
from urllib.parse import urlparse, unquote


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.strip('. ')
    return name or 'video'


def get_filename_from_url(url: str) -> str:
    parsed = urlparse(url)
    path = unquote(parsed.path)
    name = os.path.basename(path)
    if not name or '.' not in name:
        return 'video.mp4'
    return sanitize_filename(name)


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
        # Parse URL from query string or body
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
                body = self.rfile.read(length)
                data = json.loads(body)
                url = data.get('url')
            except:
                pass
        
        if not url:
            self.send_json(400, {'error': 'URL tidak ditemukan'})
            return

        # Validate URL
        try:
            parsed = urlparse(url)
            if not parsed.scheme in ('http', 'https'):
                self.send_json(400, {'error': 'URL harus http atau https'})
                return
        except:
            self.send_json(400, {'error': 'URL tidak valid'})
            return

        filename = get_filename_from_url(url)
        
        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            
            resp = urllib.request.urlopen(req, timeout=30)
            content_type = resp.headers.get('Content-Type', 'video/mp4')
            content_length = resp.headers.get('Content-Length')
            
            # Send response headers
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.send_header('Access-Control-Allow-Origin', '*')
            if content_length:
                self.send_header('Content-Length', content_length)
            self.end_headers()
            
            # Stream video data
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
                
        except urllib.error.HTTPError as e:
            self.send_json(502, {'error': f'Gagal fetch video: HTTP {e.code}'})
        except urllib.error.URLError as e:
            self.send_json(502, {'error': f'Gagal koneksi: {str(e.reason)}'})
        except Exception as e:
            self.send_json(500, {'error': f'Error: {str(e)}'})

    def send_json(self, code, data):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
