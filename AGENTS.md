# AGENTS.md

## Status

Tools download video, dibuat dengan Python.

## Commands

- **Download**: `python download.py <URL>`
- **Download dengan nama custom**: `python download.py <URL> -o output.mp4`
- **Contoh**: `python download.py https://cdn.slicedrive.com/oZWV2odR1.mp4`

## Architecture

- `download.py` - Script utama, Python standalone (tanpa dependensi external)
- Pakai stdlib (`urllib.request`) aja - gak perlu `pip install`
