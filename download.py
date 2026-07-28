#!/usr/bin/env python3
"""
Video Downloader - Download video dari URL
Cara pakai: python download.py <URL> [nama_file]
"""

import os
import sys
import re
import argparse
import urllib.request
import urllib.error
from pathlib import Path
from urllib.parse import urlparse, unquote

# Fix Windows encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


def sanitize_filename(name: str) -> str:
    """Hapus karakter yang tidak valid dari nama file."""
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.strip('. ')
    return name or 'video'


def get_filename_from_url(url: str) -> str:
    """Ambil nama file dari URL."""
    parsed = urlparse(url)
    path = unquote(parsed.path)
    name = os.path.basename(path)
    if not name or '.' not in name:
        return 'video.mp4'
    return sanitize_filename(name)


def get_file_size(url: str) -> int | None:
    """Get file size from Content-Length header."""
    try:
        req = urllib.request.Request(url, method='HEAD')
        req.add_header('User-Agent', 'Mozilla/5.0')
        with urllib.request.urlopen(req, timeout=10) as resp:
            size = resp.headers.get('Content-Length')
            return int(size) if size else None
    except Exception:
        return None


def format_size(bytes: int) -> str:
    """Format bytes to human readable."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024:
            return f"{bytes:.1f} {unit}"
        bytes /= 1024
    return f"{bytes:.1f} TB"


def download(url: str, output: str | None = None, chunk_size: int = 8192) -> Path:
    """
    Download a file from URL with progress display.
    
    Args:
        url: URL to download
        output: Output filename (auto-detected if None)
        chunk_size: Download chunk size in bytes
    
    Returns:
        Path to downloaded file
    """
    filename = output or get_filename_from_url(url)
    filepath = Path(filename)
    
    # Avoid overwriting
    counter = 1
    stem = filepath.stem
    suffix = filepath.suffix
    while filepath.exists():
        filepath = Path(f"{stem}_{counter}{suffix}")
        counter += 1

    print(f"Download: {url}")
    print(f"Menyimpan ke: {filepath}")
    
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0')
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            total = resp.headers.get('Content-Length')
            total = int(total) if total else None
            
            downloaded = 0
            with open(filepath, 'wb') as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    if total:
                        pct = (downloaded / total) * 100
                        bar_len = 30
                        filled = int(bar_len * downloaded / total)
                        bar = '#' * filled + '-' * (bar_len - filled)
                        print(f"\r  [{bar}] {pct:5.1f}% ({format_size(downloaded)}/{format_size(total)})", end='', flush=True)
                    else:
                        print(f"\r  Diunduh: {format_size(downloaded)}", end='', flush=True)
            
            print()
            print(f"\nSelesai: {filepath} ({format_size(filepath.stat().st_size)})")
            return filepath

    except urllib.error.HTTPError as e:
        print(f"Error HTTP {e.code}: {e.reason}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error Koneksi: {e.reason}")
        sys.exit(1)
    except KeyboardInterrupt:
        if filepath.exists():
            filepath.unlink()
        print("\nDownload dibatalkan.")
        sys.exit(130)


def main():
    parser = argparse.ArgumentParser(description='Download video dari URL')
    parser.add_argument('url', help='URL video yang mau didownload')
    parser.add_argument('-o', '--output', help='Nama file output')
    parser.add_argument('--chunk', type=int, default=8192, help='Ukuran chunk dalam byte')
    args = parser.parse_args()
    
    download(args.url, args.output, args.chunk)


if __name__ == '__main__':
    main()
