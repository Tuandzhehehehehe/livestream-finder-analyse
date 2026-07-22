"""
channel_crawler/linkedin_channel.py — LinkedIn Profile/Page Info Crawler
=========================================================================
Playwright + DOM scrape. Hỗ trợ Company Page (/company/) và Personal (/in/).
Dùng profile browser "linkedin" từ crawler._browser.
"""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse

from crawler._browser import launch_context
from channel_crawler._utils import extract_seller_info, parse_count, bulk_crawl
from channel_crawler.region_mapper import map_location

_PROFILE = "linkedin"
_LOGGED_OUT_KEYS = ("login", "signup", "authwall", "checkpoint")


def _parse_url(url: str) -> tuple[str, str]:
    """linkedin.com/{type}/{id} → (type, id). Raises ValueError nếu không nhận ra."""
    parts = [p for p in urlparse(url).path.strip("/").split("/") if p]
    if len(parts) >= 2 and parts[0] in ("company", "in", "school"):
        return parts[0], parts[1]
    raise ValueError(f"URL LinkedIn không hợp lệ: {url}")


def crawl_linkedin_channel(channel_url: str, use_headless: bool = True) -> Optional[dict]:
    """Crawl thông tin tổ chức/cá nhân LinkedIn. Trả về dict cho channel_repository."""
    # pyrefly: ignore [missing-import]
    from playwright.sync_api import sync_playwright

    try:
        page_type, identifier = _parse_url(channel_url)
    except ValueError as e:
        print(f"[LinkedIn] {e}")
        return None

    canonical = f"https://www.linkedin.com/{page_type}/{identifier}/"
    dom:    dict       = {}
    events: list[dict] = []

    try:
        with sync_playwright() as p:
            ctx  = launch_context(p, _PROFILE, headless=use_headless)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

            print(f"[LinkedIn] → {canonical}")
            try:
                page.goto(canonical, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)
                page.mouse.wheel(0, 3000)
                page.wait_for_timeout(1500)
            except Exception as e:
                print(f"[LinkedIn] Nav error: {e}")

            if any(k in page.url for k in _LOGGED_OUT_KEYS):
                print("[LinkedIn] ⚠ Chưa đăng nhập — chạy với use_headless=False để login")
                ctx.close()
                return None

            if page_type == "company":
                dom = page.evaluate("""() => {
                    const t = s => document.querySelector(s)?.innerText?.trim() || '';
                    const a = (s, k) => document.querySelector(s)?.getAttribute(k) || '';
                    return {
                        name:        t('h1') || t('.org-top-card-summary__title'),
                        followers:   t('.org-top-card-summary__follower-count') || t('[data-test-id="followers-count"]'),
                        description: t('.org-top-card-summary__tagline') || t('.org-about-us-organization-description__text'),
                        location:    t('.org-top-card-summary__headquarter') || t('[data-test-id="about-us__headquarters"]'),
                        industry:    t('.org-top-card-summary__industry') || t('[data-test-id="about-us__industry"]'),
                        website:     a('a[data-test-id="about-us__website"]', 'href') || t('.org-about-company-module__website'),
                        verified:    !!document.querySelector('[aria-label*="verified"]'),
                    };
                }""") or {}
                # Events tab
                try:
                    page.goto(canonical.rstrip("/") + "/events/", timeout=20000, wait_until="domcontentloaded")
                    page.wait_for_timeout(2000)
                    events = page.evaluate("""() => {
                        const out = [];
                        document.querySelectorAll('[data-view-name="organization-events-card"]').forEach(el => {
                            const title = el.querySelector('h3')?.innerText?.trim() || '';
                            const link  = el.querySelector('a')?.href || '';
                            const time  = el.querySelector('time')?.innerText?.trim() || '';
                            if (title) out.push({ type: 'event', title, url: link, date: time });
                        });
                        return out.slice(0, 10);
                    }""") or []
                except Exception:
                    pass
            else:
                dom = page.evaluate("""() => {
                    const t = s => document.querySelector(s)?.innerText?.trim() || '';
                    return {
                        name:        t('h1.text-heading-xlarge') || t('h1'),
                        followers:   t('.pvs-header__subtitle span') || t('[aria-label*="follower"]'),
                        description: t('[data-field="summary"] span') || t('.pv-about__summary-text'),
                        location:    t('.text-body-small.inline.t-black--light.break-words'),
                        industry:    t('.text-body-small.t-black--light'),
                        website:     '',
                        verified:    !!document.querySelector('[aria-label*="premium"]'),
                    };
                }""") or {}

            ctx.close()
    except Exception as e:
        print(f"[LinkedIn] Crawl error: {e}")
        return None

    if not dom.get("name"):
        print(f"[LinkedIn] Không scrape được dữ liệu: {channel_url}")
        return None

    location    = dom.get("location", "")
    description = dom.get("description") or dom.get("headline", "")
    website     = dom.get("website", "")
    region      = map_location(location)
    seller      = extract_seller_info(description, extra={
        "is_seller": page_type == "company",
        "shop_url":  website or None,
        "links":     [website] if website else [],
    })

    return {
        "platform":              "linkedin",
        "channel_id":            f"{page_type}/{identifier}",
        "channel_url":           canonical,
        "username":              identifier,
        "channel_name":          dom.get("name", identifier),
        "follower_count":        parse_count(dom.get("followers", "")),
        "broadcast_freq_weekly": None,
        "last_live_at":          None,
        "avg_viewers":           None,
        "total_livestreams":     len(events),
        "category":              dom.get("industry") or None,
        "language":              None,
        "description":           str(description)[:1000],
        "is_verified":           bool(dom.get("verified")),
        "location_raw":          location,
        "country":               region.get("country"),
        "region_tag":            region.get("region_tag"),
        "timezone":              None,
        "seller_info":           seller,
        "activity_history":      events,
        "channel_created_at":    None,
    }


def crawl_linkedin_channels_bulk(urls: list[str], use_headless: bool = True, delay_seconds: float = 4.0) -> list[dict]:
    return bulk_crawl(crawl_linkedin_channel, urls, "LinkedIn", delay=delay_seconds, use_headless=use_headless)
