#!/usr/bin/env python3
"""
Video Downloader - Auto-detect platform & download
Support: TikTok, YouTube, Facebook, Instagram, Twitter, Vimeo, Direct URL, vdy.to
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

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36'


# ─── Utility ──────────────────────────────────────────────────────

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


# ─── Platform Handlers ───────────────────────────────────────────

def handle_tiktok(url, output=None):
    """Download TikTok via tikwm.com API."""
    try:
        import requests
    except ImportError:
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'requests'], check=True)
        import requests

    print("[tiktok] Mengambil info video...")
    r = requests.post(
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

    vd = data.get('data', {})
    video_url = vd.get('play') or vd.get('wmplay')
    title = vd.get('title', 'tiktok_video')

    if not video_url:
        raise Exception("Video URL tidak ditemukan")

    filename = output or (sanitize_filename(title) + '.mp4')
    print(f"[tiktok] Judul: {title}")
    print(f"[tiktok] Download tanpa watermark...")

    headers = {'User-Agent': UA, 'Referer': 'https://www.tiktok.com/'}
    resp = requests.get(video_url, headers=headers, stream=True, timeout=60)
    resp.raise_for_status()

    total = int(resp.headers.get('Content-Length', 0)) or None
    downloaded = 0

    filepath = Path(filename)
    counter = 1
    stem = filepath.stem
    suffix = filepath.suffix
    while filepath.exists():
        filepath = Path(f"{stem}_{counter}{suffix}")
        counter += 1

    with open(filepath, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=8192):
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


def handle_protected(url, output=None):
    """Download from vdy.to / vidio.com."""
    try:
        import requests
    except ImportError:
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'requests'], check=True)
        import requests

    headers = {'User-Agent': UA}

    print("[protected] Fetch halaman utama...")
    r = requests.get(url, headers=headers, timeout=15)
    if r.status_code != 200:
        raise Exception(f"Gagal fetch: HTTP {r.status_code}")

    id_match = re.search(r"var iframeId\s*=\s*['\"]([^'\"]+)['\"]", r.text)
    token_match = re.search(r"var embedToken\s*=\s*['\"]([^'\"]+)['\"]", r.text)
    if not id_match or not token_match:
        raise Exception("iframeId/embedToken tidak ditemukan")

    domain = urlparse(url).netloc
    iframe_url = f"https://{domain}/ip129jk?id={id_match.group(1)}&t={token_match.group(1)}"
    print("[protected] Fetch player page...")
    r2 = requests.get(iframe_url, headers={**headers, 'Referer': url}, timeout=15)

    prefetch = re.search(r'prefetch.*?href=["\']([^"\']+)["\']', r2.text)
    if not prefetch:
        raise Exception("Stream URL tidak ditemukan")

    stream_url = prefetch.group(1).replace('&amp;', '&')
    print("[protected] Fetch stream page...")
    r3 = requests.get(stream_url, headers={**headers, 'Referer': iframe_url}, timeout=15)

    all_urls = re.findall(r'https?://[^\s"\'<>]+', r3.text)
    title_match = re.search(r'<title>([^<]+)</title>', r3.text)
    title = title_match.group(1).strip() if title_match else 'video'

    # Check for HLS stream first
    for u in all_urls:
        if 'm3u8' in u.lower():
            print("[protected] HLS stream detected, downloading segments...")
            filename = output or (sanitize_filename(title) + '.ts')
            return download_hls(u, filename, headers={**headers, 'Referer': stream_url})

    # Fallback to direct mp4
    video_url = None
    for u in all_urls:
        if any(x in u for x in ['mp4', 'overfetch', 'cdn']):
            if 'google' not in u and 'jquery' not in u and 'stream.php' not in u:
                video_url = u
                break

    if not video_url:
        raise Exception("URL video tidak ditemukan")

    filename = output or (sanitize_filename(title) + '.mp4')
    print("[protected] Downloading...")
    return download_direct(video_url, filename, referer=stream_url)


def download_hls(master_url, output, headers=None):
    """Download HLS: parallel segment download + merge."""
    try:
        import requests
    except ImportError:
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'requests'], check=True)
        import requests
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if not headers:
        headers = {'User-Agent': UA}

    print("[hls] Fetch master m3u8...")
    r = requests.get(master_url, headers=headers, timeout=15)
    r.raise_for_status()
    base_url = master_url.rsplit('/', 1)[0] + '/'

    lines = r.text.strip().split('\n')
    best_sub = None
    best_height = 0
    for i, line in enumerate(lines):
        m = re.search(r'RESOLUTION=\d+x(\d+)', line)
        if m:
            height = int(m.group(1))
            if i + 1 < len(lines) and not lines[i + 1].startswith('#'):
                if height > best_height:
                    best_height = height
                    best_sub = lines[i + 1].strip()

    if not best_sub:
        for line in reversed(lines):
            line = line.strip()
            if line and not line.startswith('#'):
                best_sub = line
                break

    sub_url = base_url + best_sub if not best_sub.startswith('http') else best_sub
    print(f"[hls] Best quality: {best_sub} ({best_height}p)")

    r2 = requests.get(sub_url, headers=headers, timeout=15)
    r2.raise_for_status()

    segments = [l.strip() for l in r2.text.strip().split('\n') if l.strip() and not l.startswith('#')]
    print(f"[hls] Segments: {len(segments)}")

    seg_base = sub_url.rsplit('/', 1)[0] + '/'

    def download_seg(idx_name):
        idx, seg = idx_name
        seg_url = seg if seg.startswith('http') else seg_base + seg
        for attempt in range(3):
            try:
                sr = requests.get(seg_url, headers=headers, timeout=30)
                sr.raise_for_status()
                return idx, sr.content
            except Exception as e:
                if attempt == 2:
                    raise Exception(f"Segment {seg} gagal: {e}")
                import time
                time.sleep(1)

    print(f"[hls] Downloading {len(segments)} segments (parallel 10)...")
    results = {}
    done = 0
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(download_seg, (i, s)): i for i, s in enumerate(segments)}
        for future in as_completed(futures):
            idx, data = future.result()
            results[idx] = data
            done += 1
            pct = (done / len(segments)) * 100
            size = sum(len(v) for v in results.values())
            print(f"\r  [{done}/{len(segments)}] {pct:.0f}% ({format_size(size)})", end='', flush=True)

    filepath = Path(output)
    counter = 1
    while filepath.exists():
        filepath = Path(f"{filepath.stem}_{counter}{filepath.suffix}")
        counter += 1

    with open(filepath, 'wb') as f:
        for i in range(len(segments)):
            f.write(results[i])

    print()
    print(f"Selesai: {filepath} ({format_size(filepath.stat().st_size)})")
    return filepath


def handle_youtube(url, output=None):
    """Extract direct URL from YouTube, then download."""
    import subprocess

    print("[youtube] Extracting video URL...")
    cmd = ['python', '-m', 'yt_dlp', '--no-check-certificates', '-g', '-f', 'best[ext=mp4]/best[height<=720]/best', url]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    if result.returncode != 0 or not result.stdout.strip():
        err = result.stderr.strip().split('\n')[-1] if result.stderr else 'yt-dlp gagal'
        raise Exception(err)

    video_url = result.stdout.strip().split('\n')[0]
    filename = output or 'youtube_video.mp4'
    print(f"[youtube] URL ditemukan, mengunduh...")
    return download_direct(video_url, filename, referer=url)


def handle_ytdlp(url, output=None):
    """Fallback: download via yt-dlp full download."""
    import subprocess

    outtmpl = output or '%(title)s.%(ext)s'
    print(f"[yt-dlp] Download: {url}")

    cmd = ['python', '-m', 'yt_dlp', '--no-check-certificates', '--progress', '--newline', '-o', outtmpl, url]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        raise Exception(f"yt-dlp gagal (exit code {e.returncode})")


def download_direct(url, output=None, referer=None, chunk_size=8192):
    """Download direct URL with progress bar."""
    try:
        import requests as req_lib
    except ImportError:
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'requests'], check=True)
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

    headers = {'User-Agent': UA}
    if referer:
        headers['Referer'] = referer
        parsed_referer = urlparse(referer)
        headers['Origin'] = f"{parsed_referer.scheme}://{parsed_referer.netloc}"

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


# ─── Main ─────────────────────────────────────────────────────────

def download(url, output=None):
    platform = detect_platform(url)
    print(f"Platform terdeteksi: {platform}")

    try:
        if platform == 'direct':
            return download_direct(url, output)

        elif platform == 'tiktok':
            return handle_tiktok(url, output)

        elif platform == 'youtube':
            return handle_youtube(url, output)

        elif platform == 'protected':
            return handle_protected(url, output)

        elif platform in ('instagram', 'facebook', 'twitter', 'vimeo', 'dailymotion'):
            try:
                return handle_youtube(url, output)
            except:
                print(f"[{platform}] yt-dlp extract gagal, coba full download...")
                return handle_ytdlp(url, output)

        else:
            print("[unknown] Mencoba extract...")
            try:
                return handle_protected(url, output)
            except:
                try:
                    return handle_youtube(url, output)
                except:
                    print("[unknown] Fallback ke yt-dlp...")
                    return handle_ytdlp(url, output)

    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description='Video Downloader - Auto-detect platform')
    parser.add_argument('url', help='URL video')
    parser.add_argument('-o', '--output', help='Nama file output')
    args = parser.parse_args()
    download(args.url, args.output)


if __name__ == '__main__':
    main()
