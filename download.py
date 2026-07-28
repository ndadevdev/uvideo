#!/usr/bin/env python3
"""
Video Downloader - Download video dari URL
Cara pakai: python download.py <URL> [nama_file]
Support: direct URL + situs protected (vdy.to, dll)
"""

import os
import sys
import re
import subprocess
import argparse
import urllib.request
import urllib.error
from pathlib import Path
from urllib.parse import urlparse, unquote

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

PROTECTED_SITES = ['vdy.to', 'vidio.com', 'doodstream.com', 'streamtape.com']


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


def format_size(b):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


def is_direct_url(url):
    parsed = urlparse(url)
    path = parsed.path.lower()
    return any(path.endswith(ext) for ext in ['.mp4', '.webm', '.avi', '.mov', '.mkv', '.flv', '.m3u8', '.ts'])


def is_protected_site(url):
    domain = urlparse(url).netloc.lower()
    return any(site in domain for site in PROTECTED_SITES)


# ─── Extract video URL dari situs protected ───────────────────────

def extract_vdy_url(url):
    """Extract direct video URL dari vdy.to (3 step)"""
    import requests

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    # Step 1: Fetch halaman utama → ambil iframeId & embedToken
    print("  [1/3] Fetch halaman utama...")
    r = requests.get(url, headers=headers, timeout=15)
    if r.status_code != 200:
        raise Exception(f"Gagal fetch: HTTP {r.status_code}")

    id_match = re.search(r"var iframeId\s*=\s*['\"]([^'\"]+)['\"]", r.text)
    token_match = re.search(r"var embedToken\s*=\s*['\"]([^'\"]+)['\"]", r.text)
    if not id_match or not token_match:
        raise Exception("iframeId/embedToken tidak ditemukan")

    iframe_id = id_match.group(1)
    token = token_match.group(1)

    # Step 2: Fetch halaman player (iframe)
    domain = urlparse(url).netloc
    iframe_url = f"https://{domain}/ip129jk?id={iframe_id}&t={token}"
    print(f"  [2/3] Fetch player page...")
    r2 = requests.get(iframe_url, headers={**headers, 'Referer': url}, timeout=15)

    # Step 3: Cari stream.php URL → fetch → extract video URL
    prefetch = re.search(r'prefetch.*?href=["\']([^"\']+)["\']', r2.text)
    if not prefetch:
        raise Exception("Stream URL tidak ditemukan")

    stream_url = prefetch.group(1).replace('&amp;', '&')
    print(f"  [3/3] Fetch stream page...")
    r3 = requests.get(stream_url, headers={**headers, 'Referer': iframe_url}, timeout=15)

    # Cari URL video di halaman stream
    all_urls = re.findall(r'https?://[^\s"\'<>]+', r3.text)
    for u in all_urls:
        if any(x in u for x in ['mp4', 'overfetch', 'cdn']):
            if 'google' not in u and 'jquery' not in u and 'stream.php' not in u:
                return u, stream_url

    raise Exception("URL video tidak ditemukan")


def extract_generic_url(url):
    """Generic extraction: fetch page → cari video URL"""
    import requests
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    r = requests.get(url, headers=headers, timeout=15)
    vid_match = re.search(r'(https?://[^"\'<>\s]+\.(mp4|m3u8|webm)[^"\'<>\s]*)', r.text)
    if vid_match:
        return vid_match.group(1), headers['User-Agent']
    raise Exception("URL video tidak ditemukan")


def extract_video_url(url):
    domain = urlparse(url).netloc.lower()
    if 'vdy.to' in domain:
        return extract_vdy_url(url)
    return extract_generic_url(url)


# ─── Download functions ───────────────────────────────────────────

def download_direct(url, output=None, referer=None, chunk_size=8192):
    import requests as req_lib

    filename = output or get_filename_from_url(url)
    filepath = Path(filename)

    counter = 1
    stem = filepath.stem
    suffix = filepath.suffix
    while filepath.exists():
        filepath = Path(f"{stem}_{counter}{suffix}")
        counter += 1

    print(f"Download: {url[:100]}...")
    print(f"Menyimpan ke: {filepath}")

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    if referer:
        headers['Referer'] = referer
        parsed_referer = urlparse(referer)
        headers['Origin'] = f"{parsed_referer.scheme}://{parsed_referer.netloc}"

    try:
        r = req_lib.get(url, headers=headers, stream=True, timeout=60)
        r.raise_for_status()

        total = int(r.headers.get('Content-Length', 0)) or None
        downloaded = 0

        with open(filepath, 'wb') as f:
            for chunk in r.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = (downloaded / total) * 100
                        filled = int(30 * downloaded / total)
                        bar = '#' * filled + '-' * (30 - filled)
                        print(f"\r  [{bar}] {pct:5.1f}% ({format_size(downloaded)}/{format_size(total)})", end='', flush=True)
                    else:
                        print(f"\r  Diunduh: {format_size(downloaded)}", end='', flush=True)

        print()
        print(f"Selesai: {filepath} ({format_size(filepath.stat().st_size)})")
        return filepath

    except req_lib.exceptions.HTTPError as e:
        print(f"\nError HTTP {e.response.status_code}: {e}")
        sys.exit(1)
    except req_lib.exceptions.ConnectionError as e:
        print(f"\nError Koneksi: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        if filepath.exists():
            filepath.unlink()
        print("\nDownload dibatalkan.")
        sys.exit(130)


def download_ytdlp(url, output=None):
    try:
        subprocess.run(['python', '-m', 'yt_dlp', '--version'], capture_output=True, timeout=5)
    except:
        print("Installing yt-dlp...")
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'yt-dlp'], check=True)

    outtmpl = output or '%(title)s.%(ext)s'
    print(f"Download (via yt-dlp): {url}")

    cmd = ['python', '-m', 'yt_dlp', '--no-check-certificates', '--progress', '--newline', '-o', outtmpl, url]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"\nError: yt-dlp gagal (exit code {e.returncode})")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nDownload dibatalkan.")
        sys.exit(130)


# ─── Main ─────────────────────────────────────────────────────────

def download(url, output=None, force_ytdlp=False):
    if is_direct_url(url) and not force_ytdlp:
        return download_direct(url, output)

    if is_protected_site(url) or force_ytdlp:
        try:
            print(f"Mengekstrak video URL dari situs protected...")
            video_url, referer = extract_video_url(url)
            print(f"URL video: {video_url[:80]}...")
            return download_direct(video_url, output, referer=referer)
        except Exception as e:
            print(f"Gagal extract: {e}")
            print("Fallback ke yt-dlp...")
            return download_ytdlp(url, output)

    try:
        print(f"Mencoba extract video URL...")
        video_url, referer = extract_video_url(url)
        print(f"URL video: {video_url[:80]}...")
        return download_direct(video_url, output, referer=referer)
    except:
        return download_ytdlp(url, output)


def main():
    parser = argparse.ArgumentParser(description='Download video dari URL')
    parser.add_argument('url', help='URL video')
    parser.add_argument('-o', '--output', help='Nama file output')
    parser.add_argument('--ytdlp', action='store_true', help='Paksa pake yt-dlp')
    args = parser.parse_args()
    download(args.url, args.output, args.ytdlp)


if __name__ == '__main__':
    main()
