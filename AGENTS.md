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

### Security
- Rate limiting: 10 req/min per IP
- URL validation, SSRF protection (blocks internal IPs/domains)
- Security headers in vercel.json (CSP, HSTS, X-Frame-Options: DENY)

### Known Limitations
- Instagram/Facebook/Twitter require login cookies for yt-dlp — shows friendly error on Vercel
- Vercel free tier: 10s function timeout (proxy approach bypasses this)
- No JS runtime on server — YouTube some formats may be missing

### Frontend
- Modal preview with video player after download
- Auto-clear blob URLs on modal close / download
- Progress bar with fake progress animation
- Running text ticker showing supported platforms
- Responsive (breakpoints: 768px, 480px, 360px)
