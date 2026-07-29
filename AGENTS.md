# AGENTS.md

Video downloader web tool with multi-platform auto-detection. Deployed on Vercel (free tier).

Two independent entrypoints share the same platform detection and handler logic — keep them in sync:
- `download.py` — CLI (standalone, auto-installs `requests` via subprocess pip if missing)
- `api/download.py` — Vercel serverless function (`BaseHTTPRequestHandler`, routing `/api/download`)

## Commands

```bash
python download.py <URL> [-o output.mp4]
pip install requests         # CLI auto-installs if missing; yt-dlp must be installed separately
vercel dev                   # local web dev (requires Vercel CLI)
```

## Platform Detection

`detect_platform(url)` auto-detects and routes to the right handler:

| Platform | Handler | Method |
|----------|---------|--------|
| TikTok | `handle_tiktok()` | tikwm.com API (no auth) → proxy |
| YouTube | `handle_youtube()` | `yt-dlp -g -f best[ext=mp4]/best[height<=720]/best` → proxy |
| Instagram/FB/Twitter/Vimeo/DailyMotion | try `handle_youtube()` → fallback `download_ytdlp()` full download |
| vdy.to/vidio.com/doodstream/streamtape | `handle_protected()` | 3-step extraction (iframeId/embedToken → prefetch → stream URL) → detects HLS vs MP4 |
| Direct URL (.mp4/.webm/.m3u8 etc) | `proxy_download()` | Direct proxy |

## Architecture

- `detect_platform()` logic is **duplicated** in both entrypoints — edits must be mirrored
- HLS (vdy.to): parse master m3u8 → pick best resolution → parallel segment download (10 workers, 3 retries each) → stream concatenated .ts
- API security: 10 req/min per IP rate limit, URL validation with SSRF protection (blocks internal IPs/domains), max URL 2048 chars
- Vercel free tier: 60s function timeout, no JS runtime (Python only)
- HLS output is `.ts` (MPEG-TS), playable in VLC/most modern players
- Instagram/Facebook/Twitter login required for yt-dlp — shows friendly error on Vercel

## Frontend

- UI language: **Indonesian** (all text, logs, error messages)
- Style: light theme, terminal-style (`~$` prefix), Space Mono font
- Modal after download: preview video (MIME auto-detected from extension), fallback "preview not available" for .ts
- Fake progress animation in JS (`startFakeProgress`) — not actual server progress
- Responsive breakpoints: 768px, 480px, 360px
- Blob URLs auto-cleaned on modal close

## Key Dependencies

- `requests` — in `requirements.txt`, used by both CLI and serverless function
- `yt-dlp` — **not** in `requirements.txt`, invoked via subprocess `python -m yt_dlp`; must be installed globally
- `concurrent.futures` — stdlib, used for parallel HLS segment download

## No Testing/Lint Infrastructure

No test files, test framework, lint config, type checker, or CI/CD pipeline exist. None expected.

## User Preferences

- Language: Indonesian for all UI text
- Theme: light, terminal-style (`~$` prefix)
- User prefers natural, unique UI (not AI-generated)
- Repository: `git@github.com:ndadevdev/uvideo.git`
