# Lead Discovery

Find high-potential livestreams, webinars, and events.

Features:

- Crawl livestream/event data
- AI classification
- Opportunity scoring
- Engagement suggestions

## TikTok crawling

TikTok blocks search for anonymous visitors, so its crawler drives a real
Chromium (Playwright) and reuses a persistent, logged-in browser profile. Set it
up once on a machine with a display:

```bash
python -m playwright install chromium
python -m crawler.session_login tiktok
```

A browser window opens at the login page — log in, then press Enter to save the
session. The crawler reads the structured JSON the site fetches from its own
search APIs. The login profile lives in `data/browser_profile/` (override with
the `BROWSER_PROFILE_DIR` env var).

## Benchmarking & Token Waste Analysis

Evaluate crawler performance across platforms (YouTube, TikTok, Web Search) and analyze AI token usage & waste.

### Command Line Benchmarking (`benchmark.py`)

```bash
# Run full multi-platform benchmark with default goal:
python benchmark.py --goal "AI in HR"

# Benchmark specific platforms with custom limit:
python benchmark.py --platforms youtube tiktok web --limit 5

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

## References

[1] Eric Evans, [*Domain-Driven Design: Tackling Complexity in the Heart of Software*](https://books.google.com/books?id=hHBf4YxMnWMC), Addison-Wesley, Boston, First Edition, 2003.  
[2] Google, [Google Search Central Documentation](https://developers.google.com/search/docs), Google LLC, 2025.  
[3] Google, [YouTube Data API Documentation](https://developers.google.com/youtube/v3), Google LLC, 2025.  
[4] Ian Goodfellow, Yoshua Bengio, Aaron Courville, [*Deep Learning*](https://www.deeplearningbook.org/), MIT Press, Cambridge, First Edition, 2016.  
[5] Jacob Kaplan-Moss, [*The Architecture of Open Source Applications*](https://aosabook.org/), Lulu Press, 2012.  
[6] Kent Beck, [*Implementation Patterns*](https://books.google.com/books?id=E66pB_9K_90C), Addison-Wesley, Boston, First Edition, 2007.  
[7] Martin Fowler, [*Patterns of Enterprise Application Architecture*](https://martinfowler.com/books/eaa.html), Addison-Wesley, Boston, First Edition, 2002.  
[8] OpenAI, [Prompt Engineering Guide](https://platform.openai.com/docs/guides/prompt-engineering), OpenAI, 2025.  
[9] Philip Kotler, Kevin Lane Keller, [*Marketing Management*](https://books.google.com/books?id=Z3E0CwAAQBAJ), Pearson Education, Harlow, Fifteenth Edition, 2016.  
[10] Streamlit Inc., [Streamlit Documentation](https://docs.streamlit.io/), Streamlit Inc., 2025.  
[11] Thomas H. Davenport, Rajeev Ronanki, ["Artificial Intelligence for the Real World"](https://hbr.org/2018/01/artificial-intelligence-for-the-real-world), Harvard Business Review, Vol. 96, No. 1, pp. 108–116 (2018).  
[12] W. Scott Brinker, [*Hacking Marketing: Agile Practices to Make Marketing Smarter, Faster, and More Innovative*](https://books.google.com/books?id=7I8mCwAAQBAJ), Wiley, Hoboken, First Edition, 2016.

## Graduation Internship Final Report

- [Graduation Internship Final Report (TTTN)](https://docs.google.com/document/d/13zJRIaLXOW0XvaJvyHOVYmilYZMUrngc/edit?usp=sharing&ouid=108177519104633626309&rtpof=true&sd=true)

## Defense Report

- [Defense Report](https://canva.link/jigs9z0vg28ctyw)
