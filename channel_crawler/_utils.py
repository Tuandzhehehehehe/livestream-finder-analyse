"""
channel_crawler/_utils.py — Shared helpers for all channel crawlers
====================================================================
Tránh duplicate code giữa các file crawler.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone, timedelta
from typing import Optional


_EMAIL_RE  = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_URL_RE    = re.compile(r"https?://[^\s\)\"'<>]+")
_SHOP_RE   = re.compile(r"shop|store|merch|shopee|lazada|tiki|sendo|tiktokshop|amazon|etsy|shopify|gumroad", re.I)
_BIZ_RE    = re.compile(r"\b(CEO|founder|brand|official|store|shop|business|coach|consultant)\b", re.I)
_HEADERS   = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def parse_count(s: str) -> int:
    """'1.2M' / '500K' / '10,000 followers' → int."""
    if not s:
        return 0
    s = re.sub(r"[^\d.,KMkm]", "", s.strip()).upper()
    try:
        if s.endswith("M"):
            return int(float(s[:-1]) * 1_000_000)
        if s.endswith("K"):
            return int(float(s[:-1]) * 1_000)
        return int(float(s.replace(",", "")))
    except Exception:
        return 0


def extract_seller_info(text: str, *, extra: dict | None = None) -> dict:
    """
    Trích xuất thông tin seller/creator từ chuỗi text (bio/description).

    Args:
        text:  Bio hoặc description
        extra: Các trường bổ sung để merge vào kết quả (VD: brand_name)

    Returns:
        {is_seller, contact_email, shop_url, links, bio, ...extra}
    """
    seller: dict = {
        "is_seller":     False,
        "contact_email": None,
        "shop_url":      None,
        "links":         [],
        "bio":           text[:500] if text else "",
    }
    if extra:
        seller.update(extra)

    if text:
        emails = _EMAIL_RE.findall(text)
        if emails:
            seller["contact_email"] = emails[0]

        urls = _URL_RE.findall(text)
        for u in urls:
            if _SHOP_RE.search(u):
                seller["shop_url"] = u
                seller["is_seller"] = True
                break
        seller["links"] = urls[:10]

        if _BIZ_RE.search(text):
            seller["is_seller"] = True

    return seller


def compute_freq_weekly(events: list[dict], date_key: str = "date") -> Optional[float]:
    """
    Tính số events/tuần từ danh sách events có trường date_key (ISO-8601).
    Trả về None nếu không đủ dữ liệu.
    """
    timestamps = []
    for ev in events:
        d = ev.get(date_key) or ev.get("started_at") or ev.get("date")
        if not d:
            continue
        try:
            timestamps.append(datetime.fromisoformat(str(d).replace("Z", "+00:00")))
        except Exception:
            pass
    if len(timestamps) < 2:
        return None
    timestamps.sort()
    span_days = (timestamps[-1] - timestamps[0]).days
    if span_days < 1:
        return None
    return round(len(timestamps) / (span_days / 7.0), 2)


def fetch_html(url: str, platform: str = "") -> Optional[str]:
    """GET request → HTML text, hoặc None nếu lỗi."""
    import requests
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        return resp.text if resp.status_code == 200 else None
    except Exception as e:
        tag = f"[{platform}]" if platform else ""
        print(f"{tag} HTTP error ({url}): {e}")
        return None


def first_selector(soup, selectors: list[str], attr: str | None = None) -> str:
    """
    Thử từng CSS selector, trả về text (hoặc attr) của selector đầu tiên match.
    """
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            return (el.get(attr, "") or "").strip() if attr else el.get_text(strip=True)
    return ""


def bulk_crawl(
    crawl_fn,
    urls: list[str],
    label: str,
    delay: float = 2.0,
    **kwargs,
) -> list[dict]:
    """
    Generic bulk crawl loop được dùng bởi tất cả *_channels_bulk functions.

    Args:
        crawl_fn: hàm crawl đơn (url, **kwargs) → dict | None
        urls:     danh sách URL
        label:    prefix log (VD: "YouTube", "TikTok")
        delay:    giây chờ giữa các request
    """
    results = []
    total = len(urls)
    for i, url in enumerate(urls, 1):
        print(f"[{label}] ({i}/{total}) {url}")
        try:
            data = crawl_fn(url, **kwargs)
        except Exception as e:
            print(f"[{label}] ❌ Lỗi: {e}")
            data = None
        if data:
            results.append(data)
            name = data.get("channel_name") or data.get("username") or url
            fc   = data.get("follower_count", 0)
            print(f"[{label}] ✅ {name} — {fc:,}")
        else:
            print(f"[{label}] ⚠ Bỏ qua: {url}")
        if i < total and delay > 0:
            time.sleep(delay)
    return results
