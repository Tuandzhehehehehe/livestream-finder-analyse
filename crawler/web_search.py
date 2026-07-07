import urllib.parse
from playwright.sync_api import sync_playwright
from crawler._browser import launch_context

def crawl_web(keywords, limit=20, **kwargs):
    """
    Search Google for related web articles, events, or news
    using Playwright to bypass basic bot protections.
    """
    events = []
    seen_urls = set()
    
    with sync_playwright() as p:
        # Use headless=True by default for Google to not disturb the user,
        # but since we use persistent context, it shouldn't captcha easily.
        context = launch_context(p, "google_search", headless=True)
        page = context.pages[0] if context.pages else context.new_page()
        
        try:
            for keyword in keywords[:5]: # limit to 5 keywords
                if len(events) >= limit:
                    break
                    
                # General Web Search query for events across all websites
                # Use advanced operators and action keywords to filter out blog posts and news
                # We want actual registration pages or livestreams
                # Strict livestream platforms query to avoid blog posts entirely
                query = f'"{keyword}" (site:lu.ma OR site:eventbrite.com OR site:zoom.us OR site:youtube.com OR site:twitch.tv OR site:vimeo.com OR site:meetup.com) (livestream OR webinar OR event)'
                url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"
                print(f"[Web Crawler] Searching Google for any website: {query}")
                
                try:
                    page.goto(url, timeout=30000)
                    page.wait_for_timeout(3000)
                    
                    # Check for captcha or consent wall
                    if "sorry/index" in page.url or "consent.google.com" in page.url:
                        print("[Web Crawler] Google Captcha or Consent page detected.")
                        
                    links = page.query_selector_all('h3')
                    for h3 in links:
                        a = h3.evaluate_handle('node => node.closest("a")')
                        if a:
                            href = a.get_attribute("href")
                            if href and href.startswith("http") and not "google.com" in href:
                                # Ensure it's actually a livestream/event domain
                                allowed_domains = ["lu.ma", "eventbrite.com", "zoom.us", "youtube.com", "twitch.tv", "vimeo.com", "meetup.com", "linkedin.com/events"]
                                if not any(d in href for d in allowed_domains):
                                    continue
                                
                                if href in seen_urls:
                                    continue
                                seen_urls.add(href)
                                
                                title = h3.inner_text().strip()
                                snippet = "Kết quả tìm kiếm từ Google Web Search."
                                try:
                                    container = h3.evaluate_handle('node => { let el = node; while(el && !el.classList.contains("g") && el.tagName !== "BODY") { el = el.parentElement; } return el.tagName !== "BODY" ? el : node.parentElement.parentElement; }')
                                    if container:
                                        snippet = container.inner_text().replace('\\n', ' ')
                                except Exception:
                                    pass

                                if title:
                                    import re as _re
                                    from datetime import datetime as _dt
                                    current_year = _dt.now().year

                                    # Tìm năm trong title hoặc snippet
                                    years_found = [int(y) for y in _re.findall(r'\b(20\d{2})\b', title + ' ' + snippet)]

                                    event_status = "UPCOMING"
                                    skip = False
                                    if years_found:
                                        min_year = min(years_found)
                                        if min_year < current_year:
                                            # Năm cũ hơn năm hiện tại → đã qua, bỏ qua
                                            skip = True
                                        elif min_year > current_year + 1:
                                            # Năm quá xa trong tương lai → bỏ qua
                                            skip = True

                                    if skip:
                                        continue

                                    events.append({
                                        "platform": "Web",
                                        "keyword": keyword,
                                        "title": title,
                                        "url": href,
                                        "start_time": "",
                                        "status": event_status,
                                        "description": snippet
                                    })
                                    if len(events) >= limit:
                                        break
                except Exception as e:
                    print(f"[Web Crawler] Search error for '{query}': {e}")
                    
        except Exception as e:
            print(f"[Web Crawler] Init error: {e}")
        finally:
            try:
                context.close()
            except:
                pass
                
    return events
