# Lead Discovery

Find high-potential livestreams, webinars, and events.

Features:

- Crawl livestream/event data
- AI classification
- Opportunity scoring
- Engagement suggestions

## X & TikTok crawling

X and TikTok block search for anonymous visitors, so their crawlers drive a real
Chromium (Playwright) and reuse a persistent, logged-in browser profile. Set it
up once per platform on a machine with a display:

```bash
python -m playwright install chromium
python -m crawler.session_login x
python -m crawler.session_login tiktok
```

A browser window opens at the login page — log in, then press Enter to save the
session. The crawlers read the structured JSON the sites fetch from their own
search APIs. The login profile lives in `data/browser_profile/` (override with
the `BROWSER_PROFILE_DIR` env var).

## Benchmarking & Token Waste Analysis

Evaluate crawler performance across platforms (YouTube, Meetup, LinkedIn, X, TikTok, Web Search) and analyze AI token usage & waste.

### Command Line Benchmarking (`benchmark.py`)

```bash
# Run full multi-platform benchmark with default goal:
python benchmark.py --goal "AI in HR"

# Benchmark specific platforms with custom limit:
python benchmark.py --platforms youtube meetup web --limit 5

# Run raw crawler performance test only (no AI token usage):
python benchmark.py --no-ai

# View previously saved benchmark reports:
python benchmark.py --list-reports
```

### Real-Time Token Monitor (`track_tokens.py`)

```bash
# Monitor AI token consumption and category breakdown in real-time:
python track_tokens.py
```

### Interactive Dashboard

Launch the Streamlit web app to access the interactive **⚡ Benchmark & Token Waste** tab:

```bash
streamlit run dashboard/streamlit_app.py
```

