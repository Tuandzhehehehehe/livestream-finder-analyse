"""
channel_crawler/web_channel.py — Generic Web Channel Crawler
=============================================================
Crawl thông tin kênh/creator từ website bất kỳ (không cần API key).
Dùng requests + BeautifulSoup để đọc metadata từ:
  - Open Graph / Twitter Card tags
  - JSON-LD schema.org (Person, Organization, WebSite, ProfilePage)
  - <meta name="description">, <title>, <html lang>
"""

from __future__ import annotations

import re
import json
from typing import Optional
from urllib.parse import urlparse

from channel_crawler._utils import extract_seller_info, bulk_crawl, parse_count, _SHOP_RE, _HEADERS
from channel_crawler.region_mapper import map_location

_TIMEOUT = 15


def _get_html(url: str) -> Optional[str]:
    try:
        import requests  # pyrefly: ignore [missing-import]
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT, allow_redirects=True)
        return resp.text if resp.status_code == 200 else None
    except Exception as e:
        print(f"[Web] HTTP error ({url}): {e}")
    return None


# ── Metadata helpers ──────────────────────────────────────────────────────────

def _og(soup, prop: str) -> str:
    """Lấy content của <meta property="og:X"> hoặc <meta name="X">."""
    for attr in ("property", "name"):
        tag = soup.find("meta", attrs={attr: prop})
        if tag:
            return (tag.get("content") or "").strip()
    return ""


def _json_ld_objects(soup) -> list[dict]:
    objects = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
            if isinstance(data, list):
                objects.extend(data)
            elif isinstance(data, dict):
                objects.append(data)
        except Exception:
            pass
    return objects


def _pick_schema(objects: list[dict], *types: str) -> Optional[dict]:
    target = {t.lower() for t in types}
    for obj in objects:
        raw = obj.get("@type", "")
        for t in ([raw] if isinstance(raw, str) else raw):
            if t.lower() in target:
                return obj
    return None


def _schema_str(obj: dict, key: str) -> str:
    """Lấy giá trị string từ JSON-LD object (hỗ trợ @value và list)."""
    v = obj.get(key)
    if isinstance(v, str):    return v.strip()
    if isinstance(v, dict):   return (v.get("@value") or v.get("name") or "").strip()
    if isinstance(v, list) and v:
        first = v[0]
        if isinstance(first, str): return first.strip()
        if isinstance(first, dict): return (first.get("@value") or first.get("name") or "").strip()
    return ""


def _follower_count(soup, json_ld: list[dict], page_text: str) -> Optional[int]:
    # JSON-LD interactionStatistic
    for obj in json_ld:
        stats = obj.get("interactionStatistic") or []
        if isinstance(stats, dict):
            stats = [stats]
        for stat in stats:
            itype = (stat.get("interactionType") or {}).get("@type", "")
            if "Follow" in itype or "Subscribe" in itype:
                try:
                    return int(stat["userInteractionCount"])
                except Exception:
                    pass
    # Text heuristic
    m = re.search(
        r"([\d,\.]+[KkMmBb]?)\s*(?:followers?|subscribers?|người đăng ký|người theo dõi)",
        page_text, re.IGNORECASE,
    )
    if m:
        val = parse_count(m.group(1))
        return val if val > 0 else None
    return None


def _detect_language(soup) -> Optional[str]:
    html_tag = soup.find("html")
    if html_tag and html_tag.get("lang"):
        return html_tag["lang"].split("-")[0].lower()
    locale = _og(soup, "og:locale")
    return locale.split("_")[0].lower() if locale else None


def _extract_location(json_ld: list[dict]) -> str:
    for obj in json_ld:
        addr = obj.get("address") or {}
        if isinstance(addr, dict):
            loc = ", ".join(p for p in [
                addr.get("addressLocality", ""),
                addr.get("addressRegion", ""),
                addr.get("addressCountry", ""),
            ] if p)
            if loc:
                return loc
        for key in ("location", "foundingLocation", "homeLocation"):
            v = obj.get(key)
            if isinstance(v, str) and v.strip(): return v.strip()
            if isinstance(v, dict) and v.get("name"): return v["name"]
    return ""


# ── Main crawl ────────────────────────────────────────────────────────────────

def crawl_web_channel(channel_url: str) -> Optional[dict]:
    """Crawl thông tin kênh từ website bất kỳ. Trả về dict cho channel_repository."""
    try:
        from bs4 import BeautifulSoup  # pyrefly: ignore [missing-import]
    except ImportError:
        print("[Web] beautifulsoup4 chưa cài. Chạy: pip install beautifulsoup4")
        return None

    if not channel_url.startswith(("http://", "https://")):
        channel_url = "https://" + channel_url

    parsed = urlparse(channel_url)
    domain = parsed.netloc.lstrip("www.")

    html = _get_html(channel_url)
    if not html:
        print(f"[Web] Không tải được trang: {channel_url}")
        return None

    soup     = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(separator=" ", strip=True)[:5000]
    json_ld  = _json_ld_objects(soup)
    entity   = _pick_schema(json_ld, "WebSite", "Organization", "Person", "ProfilePage")

    # ── Tên kênh ──────────────────────────────────────────────────────────────
    channel_name = (
        _og(soup, "og:site_name")
        or (entity and _schema_str(entity, "name"))
        or _og(soup, "og:title")
        or (soup.find("title").get_text(strip=True) if soup.find("title") else "")
        or domain
    )
    channel_name = re.split(r"\s*[|–—\-]\s*", channel_name)[0].strip() or domain

    # ── Description ───────────────────────────────────────────────────────────
    description = (
        _og(soup, "og:description")
        or (entity and _schema_str(entity, "description"))
        or _og(soup, "twitter:description")
    )
    if not description:
        tag = soup.find("meta", attrs={"name": "description"})
        description = (tag.get("content") or "").strip() if tag else ""

    # ── Canonical URL ─────────────────────────────────────────────────────────
    ctag = soup.find("link", rel="canonical")
    canonical = (ctag["href"] if ctag and ctag.get("href") else channel_url).strip()
    cp = urlparse(canonical)
    if cp.path and cp.path != "/":
        canonical = f"{cp.scheme}://{cp.netloc}"

    # ── Seller info ───────────────────────────────────────────────────────────
    seller = extract_seller_info(description + " " + page_text[:1000])
    og_url = _og(soup, "og:url")
    if og_url and not seller.get("shop_url") and _SHOP_RE.search(og_url):
        seller["shop_url"] = og_url
        seller["is_seller"] = True

    # Social links từ schema sameAs
    pe = _pick_schema(json_ld, "Person", "Organization", "Brand")
    if pe:
        same_as = pe.get("sameAs") or []
        seller.setdefault("social_links", ([same_as] if isinstance(same_as, str) else same_as)[:5])

    # ── Location ──────────────────────────────────────────────────────────────
    location_raw = _extract_location(json_ld)
    region       = map_location(location_raw)

    print(f"[Web] ✅ {channel_name} | {domain}")

    return {
        "platform":              "web",
        "channel_id":            domain.replace(".", "_"),
        "channel_url":           canonical,
        "username":              domain,
        "channel_name":          channel_name,
        "follower_count":        _follower_count(soup, json_ld, page_text) or 0,
        "broadcast_freq_weekly": None,
        "last_live_at":          None,
        "avg_viewers":           None,
        "total_livestreams":     0,
        "category":              None,
        "language":              _detect_language(soup),
        "description":           description[:1000],
        "is_verified":           False,
        "location_raw":          location_raw,
        "country":               region.get("country"),
        "region_tag":            region.get("region_tag"),
        "timezone":              None,
        "seller_info":           seller,
        "activity_history":      [],
        "channel_created_at":    None,
    }


def crawl_web_channels_bulk(urls: list[str], **_) -> list[dict]:
    return bulk_crawl(crawl_web_channel, urls, "Web", delay=1.0)
