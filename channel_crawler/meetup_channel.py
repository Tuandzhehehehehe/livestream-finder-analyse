"""
channel_crawler/meetup_channel.py — Meetup Group Info Crawler
=============================================================
requests + BeautifulSoup. Không cần login.
URL: https://www.meetup.com/{group-slug}/
"""

from __future__ import annotations

import re
from typing import Optional

from bs4 import BeautifulSoup  # pyrefly: ignore [missing-import]

from channel_crawler._utils import (
    extract_seller_info, fetch_html, first_selector,
    compute_freq_weekly, parse_count, bulk_crawl,
)
from channel_crawler.region_mapper import map_location

_SYSTEM_SLUGS = {"find", "topics", "cities", "pro", "search", "events", "api"}


def _slug(url: str) -> Optional[str]:
    m = re.search(r"meetup\.com/([^/?#]+)/?", url)
    s = m.group(1) if m else None
    return None if s in _SYSTEM_SLUGS else s


def _parse(html: str) -> dict:
    soup   = BeautifulSoup(html, "html.parser")
    result = {"name": "", "description": "", "members": 0, "location": "", "category": "", "organizer": "", "events": []}

    h1 = soup.find("h1")
    if h1:
        result["name"] = h1.get_text(strip=True)

    # Member count — regex first (most reliable)
    for pat in [r"([\d,]+)\s+member", r"member[s]?\s*[:\-]\s*([\d,]+)", r'"members"\s*:\s*(\d+)']:
        m = re.search(pat, html, re.I)
        if m:
            result["members"] = int(m.group(1).replace(",", ""))
            break
    if not result["members"]:
        result["members"] = parse_count(first_selector(soup, [
            "[data-testid='members-count']", ".groupHomeHeader-memberCount", ".groupMetaData-memberCount",
        ]))

    result["description"] = first_selector(soup, [
        "[data-testid='group-about-description']", ".group-description",
        "#about .text--body", "section[aria-label='About'] p",
    ])[:1000]

    result["location"] = first_selector(soup, [
        "[data-testid='group-location']", ".groupHomeHeader-locationAndCategory",
        ".groupLocation", "address",
    ])
    if not result["location"]:
        m = re.search(r'"addressLocality"\s*:\s*"([^"]+)"', html)
        if m:
            result["location"] = m.group(1)

    tags = soup.select(".groupTopics a") or soup.select("[data-testid='group-topics'] a") or soup.select(".topic-tag")
    if tags:
        result["category"] = ", ".join(t.get_text(strip=True) for t in tags[:3])

    result["organizer"] = first_selector(soup, [
        "[data-testid='organizer-name']", ".organizer-name",
        ".groupOrganizer-name", "a[href*='/members/']",
    ])

    seen = set()
    for card in soup.find_all("a", {"data-event-label": "Event Card"}):
        href = card.get("href", "")
        if not href or href in seen:
            continue
        seen.add(href)
        h3    = card.find("h3")
        title = h3.get_text(strip=True) if h3 else card.get_text(strip=True)[:100]
        if not title:
            continue
        time_el   = card.find("time")
        date_str  = (time_el.get("datetime") or time_el.get_text(strip=True)) if time_el else ""
        att_el    = card.find(lambda t: t.name == "span" and "attendee" in t.get_text("", strip=True).lower())
        result["events"].append({
            "type":      "event",
            "title":     title,
            "url":       href,
            "date":      date_str,
            "attendees": att_el.get_text(strip=True) if att_el else "",
        })

    return result


def crawl_meetup_channel(channel_url: str) -> Optional[dict]:
    """Crawl group Meetup. Trả về dict cho channel_repository."""
    slug = _slug(channel_url)
    if not slug:
        print(f"[Meetup] URL không hợp lệ: {channel_url}")
        return None

    canonical = f"https://www.meetup.com/{slug}/"
    print(f"[Meetup] → {canonical}")

    html = fetch_html(canonical, "Meetup")
    if not html:
        return None

    grp = _parse(html)
    if not grp["name"]:
        print(f"[Meetup] Không tìm được tên group: {canonical}")
        return None

    region = map_location(grp["location"])
    seller = extract_seller_info(grp["description"], extra={
        "organizer": grp["organizer"],
    })

    return {
        "platform":              "meetup",
        "channel_id":            slug,
        "channel_url":           canonical,
        "username":              slug,
        "channel_name":          grp["name"],
        "follower_count":        grp["members"],
        "broadcast_freq_weekly": compute_freq_weekly(grp["events"]),
        "last_live_at":          grp["events"][0].get("date") if grp["events"] else None,
        "avg_viewers":           None,
        "total_livestreams":     len(grp["events"]),
        "category":              grp["category"] or None,
        "language":              None,
        "description":           grp["description"],
        "is_verified":           False,
        "location_raw":          grp["location"],
        "country":               region.get("country"),
        "region_tag":            region.get("region_tag"),
        "timezone":              None,
        "seller_info":           seller,
        "activity_history":      grp["events"][:10],
        "channel_created_at":    None,
    }


def crawl_meetup_channels_bulk(urls: list[str], delay_seconds: float = 2.0) -> list[dict]:
    return bulk_crawl(crawl_meetup_channel, urls, "Meetup", delay=delay_seconds)
