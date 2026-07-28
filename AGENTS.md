# AGENTS.md

## Project: uvideo

Video downloader web tool with multi-platform auto-detection. Deployed on Vercel (free tier).

## Commands

- **CLI download**: `python download.py <URL> [-o output.mp4]`
- **Web**: Deploy to Vercel, visit the URL
- **Test TikTok**: `python download.py "https://www.tiktok.com/..." -o test.mp4`

## Architecture

### Platform Detection
`detect_platform(url)` auto-detects and routes to the right handler:

| Platform | Handler | Method |
|----------|---------|--------|
| TikTok | `handle_tiktok()` | tikwm.com API → proxy |
| YouTube | `handle_youtube()` | yt-dlp `-g` extract URL → proxy |
| Instagram/FB/Twitter | `handle_youtube()` | yt-dlp extract → fallback `download_ytdlp()` |
| vdy.to / vidio.com | `handle_protected()` | Custom 3-step extraction → proxy |
| vdy.to (HLS) | `handle_protected()` + `proxy_hls()` | Parse m3u8 → parallel segment download → stream |
| Direct URL (.mp4 etc) | `proxy_download()` | Direct proxy |

### Files
- `download.py` — CLI tool (standalone, uses stdlib + requests + yt-dlp)
- `api/download.py` — Vercel serverless function
- `index.html` — Web UI (light theme, modal preview, auto-cache cleanup)
- `vercel.json` — Vercel config + security headers
- `requirements.txt` — Python deps (`requests`)
- `.gitignore` — Excludes video files, caches, node_modules

### Key APIs
- **tikwm.com** — Free TikTok API (no auth), returns video URL without watermark
- **yt-dlp** — Social media extraction (`-g` flag for URL-only mode)
- YouTube extracts fastest with `-g -f best[ext=mp4]`

### HLS Handling
vdy.to streams use HLS (.m3u8 + .ts segments). The proxy:
1. Fetches master m3u8, picks best resolution (720p)
2. Fetches sub-m3u8 for segment list
3. Downloads ALL segments in parallel (10 workers, 3 retries each)
4. Streams concatenated .ts data to client

### Security
- Rate limiting: 10 req/min per IP
- URL validation, SSRF protection (blocks internal IPs/domains)
- Security headers in vercel.json (CSP, HSTS, X-Frame-Options: DENY)

### Known Limitations
- Instagram/Facebook/Twitter require login cookies for yt-dlp — shows friendly error on Vercel
- Vercel free tier: 60s function timeout (parallel HLS download fits within this)
- No JS runtime on server — YouTube some formats may be missing
- HLS output is .ts format (MPEG-TS), playable in VLC and most modern players

### Frontend
- Modal preview with video player after download
- Auto-clear blob URLs on modal close / download
- Progress bar with fake progress animation
- Running text ticker showing supported platforms
- Responsive (breakpoints: 768px, 480px, 360px)

## Session History

### Session 1 (July 28, 2026)
- Built video downloader web tool from scratch
- Implemented CLI (`download.py`) and web UI (`index.html` + `api/download.py`)
- Deployed to Vercel (free tier)
- Added security: rate limiting, URL validation, SSRF protection, security headers
- Added responsive design, terminal-style UI, running text ticker

### Session 2 (July 28, 2026)
- Fixed TikTok download — yt-dlp fails with 403, switched to tikwm.com API
- Added auto-platform detection (`detect_platform()`) for TikTok, YouTube, Instagram, Facebook, Twitter, vdy.to, direct URLs
- Added auto-clear cache/blob after download (modal cleanup)
- Fixed modal preview popup (was auto-downloading instead of showing preview)
- Updated AGENTS.md with project facts

### Session 3 (July 28, 2026)
- Tested all platforms: YouTube ✓, TikTok ✓, vdy.to ✓, Instagram ✗ (needs login), Facebook ✗ (needs login), Twitter ✗ (needs login)
- Added YouTube URL extraction via yt-dlp `-g` flag → proxy (faster than full download)
- Added friendly error messages per platform for unsupported ones
- Added HLS support for vdy.to: parse master.m3u8 → fetch segments → parallel download (10 workers, 3 retries)
- Fixed vdy.to returning master.m3u8 instead of video — was not handling HLS streams
- Added parallel segment download (71 segments in ~60s vs timeout before)
- Added retry logic for HLS segment downloads

### Session 4 (July 28, 2026)
- Fixed video preview: added MIME type detection for blob creation (`.ts` → `video/mp2t`, `.mp4` → `video/mp4`)
- Added clear button (×) on URL input field
- Added modal preview fallback: shows "preview not available" message for unsupported formats (.ts MPEG-TS)
- Added UV favicon to browser tab (inline SVG: dark bg, blue U, white V)
- Added `modalNoPreview` element for unsupported format feedback

## User Preferences
- Language: Indonesian for UI text
- Theme: light, terminal-style (`~$` prefix)
- User GitHub: `git@github.com:ndadevdev/uvideo.git`
- User prefers natural, unique UI (not AI-generated looking)
- User communicates in Indonesian
