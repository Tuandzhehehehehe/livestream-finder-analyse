"""
channel_crawler/eventbrite_channel.py — Eventbrite Organizer Info Crawler
==========================================================================
requests + BeautifulSoup. Không cần login.
URL: https://www.eventbrite.com/o/{slug}/
"""

from __future__ import annotations

import re
from typing import Optional

from bs4 import BeautifulSoup  # pyrefly: ignore [missing-import]

from channel_crawler._utils import extract_seller_info, fetch_html, first_selector, bulk_crawl
from channel_crawler.region_mapper import map_location


def _slug(url: str) -> Optional[str]:
    m = re.search(r"eventbrite\.com/o/([^/?#]+)", url)
    return m.group(1) if m else None


def _parse(html: str) -> dict:
    soup   = BeautifulSoup(html, "html.parser")
    result = {"name": "", "description": "", "followers": 0, "location": "", "website": "", "events": []}

    h1 = soup.find("h1")
    if h1:
        result["name"] = h1.get_text(strip=True)

    result["description"] = first_selector(soup, [
        "[data-testid='organizer-description']",
        ".organizer-profile__description",
        ".js-organizer-description",
    ])[:1000]

    # Follower count — regex on raw HTML (most reliable)
    for pat in [r"([\d,]+)\s+follower", r"follower[s]?\s*:\s*([\d,]+)"]:
        m = re.search(pat, html, re.I)
        if m:
            result["followers"] = int(m.group(1).replace(",", ""))
            break

    result["location"] = first_selector(soup, [
        "[data-testid='organizer-location']",
        ".organizer-profile__location",
        "[data-automation='organizer-location']",
    ])
    if not result["location"]:
        m = re.search(r'"addressLocality"\s*:\s*"([^"]+)"', html)
        if m:
            result["location"] = m.group(1)

    for link in soup.find_all("a", href=True):
        href = link["href"]
        if href.startswith("http") and "eventbrite.com" not in href:
            result["website"] = href
            break

    seen = set()
    for card in soup.find_all("a", href=lambda h: h and "/e/" in h):
        href = card.get("href", "")
        if not href or href in seen:
            continue
        seen.add(href)
        title_el = card.find(["h2", "h3", "h4"])
        title = (title_el.get_text(strip=True) if title_el else card.get_text(strip=True)[:100])
        if not title or len(title) < 5:
            continue
        time_el  = card.find("time")
        date_str = (time_el.get("datetime") or time_el.get_text(strip=True)) if time_el else ""
        result["events"].append({"type": "event", "title": title, "url": href, "date": date_str})

    return result


def crawl_eventbrite_channel(channel_url: str) -> Optional[dict]:
    """Crawl organizer Eventbrite. Trả về dict cho channel_repository."""
    slug = _slug(channel_url)
    if not slug:
        print(f"[Eventbrite] URL không hợp lệ: {channel_url}")
        return None

    canonical = f"https://www.eventbrite.com/o/{slug}/"
    print(f"[Eventbrite] → {canonical}")

    html = fetch_html(canonical, "Eventbrite")
    if not html:
        return None

    org = _parse(html)
    if not org["name"]:
        print(f"[Eventbrite] Không tìm được tên: {canonical}")
        return None

    region = map_location(org["location"])
    seller = extract_seller_info(org["description"], extra={
        "is_seller": True,
        "shop_url":  org["website"] or None,
        "links":     [org["website"]] if org["website"] else [],
    })

    return {
        "platform":              "eventbrite",
        "channel_id":            slug,
        "channel_url":           canonical,
        "username":              slug,
        "channel_name":          org["name"],
        "follower_count":        org["followers"],
        "broadcast_freq_weekly": None,
        "last_live_at":          org["events"][0].get("date") if org["events"] else None,
        "avg_viewers":           None,
        "total_livestreams":     len(org["events"]),
        "category":              None,
        "language":              None,
        "description":           org["description"],
        "is_verified":           False,
        "location_raw":          org["location"],
        "country":               region.get("country"),
        "region_tag":            region.get("region_tag"),
        "timezone":              None,
        "seller_info":           seller,
        "activity_history":      org["events"][:10],
        "channel_created_at":    None,
    }


def crawl_eventbrite_channels_bulk(urls: list[str], delay_seconds: float = 2.0) -> list[dict]:
    return bulk_crawl(crawl_eventbrite_channel, urls, "Eventbrite", delay=delay_seconds)
