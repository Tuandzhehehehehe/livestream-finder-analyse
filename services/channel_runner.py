"""
services/channel_runner.py — Channel Intelligence Pipeline
==========================================================
Điều phối luồng channel intelligence:
  1. Crawl kênh từ URL → upsert DB (crawl_and_save_channels)
  2. Auto-crawl kênh sau khi tìm livestream (enqueue_channels_from_events)
  3. Làm mới CAS + growth (refresh_channel_scores)
  4. Xếp hạng & đề xuất theo khu vực (run_channel_pipeline)
"""

from __future__ import annotations

import csv
import importlib
import io
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

# ── Logger ─────────────────────────────────────────────────────────────────────
_DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data"))
os.makedirs(_DATA_DIR, exist_ok=True)

logger = logging.getLogger("channel_runner")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    for _h in (
        logging.FileHandler(os.path.join(_DATA_DIR, "channel_run.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ):
        _h.setFormatter(_fmt)
        logger.addHandler(_h)


# ── Platform crawlers ──────────────────────────────────────────────────────────

_CRAWLERS: dict[str, str] = {
    "youtube":    "channel_crawler.youtube_channel.crawl_youtube_channels_bulk",
    "tiktok":     "channel_crawler.tiktok_channel.crawl_tiktok_channels_bulk",
    "web":        "channel_crawler.web_channel.crawl_web_channels_bulk",
}


def _get_crawl_fn(platform: str):
    dotpath = _CRAWLERS.get(platform.lower())
    if not dotpath:
        raise ValueError(f"Platform không hỗ trợ: '{platform}'. Dùng: {list(_CRAWLERS)}")
    mod_path, fn_name = dotpath.rsplit(".", 1)
    return getattr(importlib.import_module(mod_path), fn_name)


# ── Crawl + lưu DB ─────────────────────────────────────────────────────────────

def crawl_and_save_channels(urls: list[str], platform: str, *, max_live_history: int = 20, goal: str = "", target_region: str = "") -> dict:
    """Crawl danh sách URL kênh, tính CAS và upsert vào channel_info.db."""
    from database.channel_repository import upsert_channel
    from services.attraction_score import compute_cas, cas_tier

    logger.info(f"[{platform.upper()}] Crawl {len(urls)} URL...")
    try:
        kwargs = {"max_live_history": max_live_history} if platform == "youtube" else {}
        raw: list[dict] = _get_crawl_fn(platform)(urls, **kwargs)
    except Exception as e:
        logger.error(f"[{platform.upper()}] Lỗi: {e}")
        return {"crawled": len(urls), "saved": 0, "skipped": len(urls), "channels": []}

    saved, skipped = [], 0
    for ch in raw:
        if not ch:
            skipped += 1
            continue
        if goal:
            if not ch.get("category"):
                ch["category"] = goal
            s_info = dict(ch.get("seller_info") or {}) if isinstance(ch.get("seller_info"), dict) else {}
            goals = set(s_info.get("search_goals") or [])
            goals.add(goal)
            s_info["search_goals"] = list(goals)
            ch["seller_info"] = s_info

        if target_region:
            from channel_crawler.region_mapper import map_location
            loc = map_location(target_region)
            if not ch.get("country"):
                ch["country"] = loc.get("country") or target_region.split("-")[0].upper()
            if not ch.get("region_tag"):
                ch["region_tag"] = loc.get("region_tag") or target_region

        ch["cas"] = compute_cas(ch)
        ch["cas_computed_at"] = datetime.now(timezone.utc)
        ch["tier"] = cas_tier(ch["cas"])
        if upsert_channel(ch):
            saved.append(ch)
            logger.info(f"  ✔ {ch.get('channel_name', ch.get('channel_url', '?'))[:50]} | CAS={ch['cas']}")
        else:
            skipped += 1
            logger.warning(f"  ✘ Lưu thất bại: {ch.get('channel_url', '?')}")

    skipped += len(urls) - len(raw)
    logger.info(f"[{platform.upper()}] Hoàn tất: {len(saved)} lưu | {skipped} bỏ qua")
    return {"crawled": len(urls), "saved": len(saved), "skipped": skipped, "channels": saved}


# ── Auto-crawl channel từ livestream events ────────────────────────────────────

def _infer_channel_url(event_url: str, platform: str) -> str:
    """
    Suy luận channel URL từ URL của một livestream event.

    Hỗ trợ:
      - YouTube: /channel/<id>, /@handle, /c/<handle>, /user/<user>
      - YouTube watch?v=VIDEO_ID → resolve channelId qua YouTube Data API
      - TikTok: /@<username>, /video/<id> (lấy author từ URL path)
      - Web: trả về origin URL làm channel URL (homepage)
    """
    if not event_url:
        return ""
    p = urlparse(event_url)
    path_parts = [s for s in p.path.split("/") if s]

    if platform == "youtube":
        path = p.path.rstrip("/")
        # Đã là channel URL
        if "/channel/" in path or path.startswith("/@") or "/c/" in path or "/user/" in path:
            return f"https://youtube.com{path}"
        # watch?v=VIDEO_ID → resolve về channel URL qua API
        video_match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", event_url)
        if video_match:
            return _resolve_youtube_channel_from_video(video_match.group(1))
        return ""

    if platform == "tiktok":
        if path_parts and path_parts[0].startswith("@"):
            return f"https://tiktok.com/{path_parts[0]}"
        # /video/ID → không có username trong URL, bỏ qua
        return ""

    if platform == "web":
        # Dùng origin (scheme + netloc) làm đại diện channel
        if p.scheme and p.netloc:
            return f"{p.scheme}://{p.netloc}"
        return ""

    return ""


def _resolve_youtube_channel_from_video(video_id: str) -> str:
    """
    Dùng YouTube Data API để lấy channelId từ videoId.
    Trả về channel URL hoặc chuỗi rỗng nếu không resolve được.
    """
    import os
    key = os.getenv("YOUTUBE_API_KEY")
    if not key:
        logger.debug("[YouTube] YOUTUBE_API_KEY chưa cấu hình, bỏ qua resolve video→channel")
        return ""
    try:
        from googleapiclient.discovery import build  # pyrefly: ignore [missing-import]
        yt = build("youtube", "v3", developerKey=key)
        resp = yt.videos().list(part="snippet", id=video_id).execute()
        items = resp.get("items", [])
        if not items:
            return ""
        ch_id = items[0]["snippet"].get("channelId", "")
        return f"https://youtube.com/channel/{ch_id}" if ch_id else ""
    except Exception as e:
        logger.debug(f"[YouTube] resolve video→channel error ({video_id}): {e}")
        return ""


def enqueue_channels_from_events(events: list[dict], goal: str = "", target_region: str = "") -> dict:
    """
    Trích channel URL từ events, bổ sung meta (goal, region), crawl batch mới.
    Trả về: {new_urls, skipped_existing, saved, skipped_crawl}
    """
    from database.channel_repository import get_channel_by_url, enrich_channel_meta

    # Trích (platform, url) duy nhất từ events
    seen: set[str] = set()
    pairs: list[tuple[str, str]] = []
    for ev in events:
        platform = (ev.get("platform") or "").lower()
        if not platform:
            continue
        url = ev.get("channel_url", "").strip() or _infer_channel_url(ev.get("url", ""), platform)
        if url and url not in seen:
            seen.add(url)
            pairs.append((platform, url))

    if not pairs:
        return {"new_urls": 0, "skipped_existing": 0, "saved": 0, "skipped_crawl": 0}

    # Lọc URL chưa có trong DB, gom theo platform
    to_crawl: dict[str, list[str]] = {}
    skipped_existing = 0
    for platform, url in pairs:
        if get_channel_by_url(url):
            skipped_existing += 1
            if goal or target_region:
                enrich_channel_meta(url, goal=goal, target_region=target_region)
        else:
            to_crawl.setdefault(platform, []).append(url)

    if not to_crawl:
        logger.info(f"[AutoChannel] {skipped_existing} channel đã có trong DB")
        return {"new_urls": len(pairs), "skipped_existing": skipped_existing, "saved": 0, "skipped_crawl": 0}

    saved = skipped_crawl = 0
    for platform, urls in to_crawl.items():
        try:
            s = crawl_and_save_channels(urls, platform, goal=goal, target_region=target_region)
            saved        += s["saved"]
            skipped_crawl += s["skipped"]
        except Exception as e:
            logger.warning(f"[AutoChannel] {platform}: {e}")
            skipped_crawl += len(urls)

    logger.info(f"[AutoChannel] {saved} lưu | {skipped_existing} đã có | {skipped_crawl} lỗi")
    return {"new_urls": len(pairs), "skipped_existing": skipped_existing, "saved": saved, "skipped_crawl": skipped_crawl}



# ── Làm mới điểm số ────────────────────────────────────────────────────────────

def refresh_channel_scores(*, refresh_growth: bool = True) -> dict:
    """Tính lại CAS (và tuỳ chọn growth trend) cho toàn bộ kênh trong DB."""
    from database.channel_repository import refresh_all_cas, refresh_growth_trends

    cas_n = refresh_all_cas()
    logger.info(f"🔄 CAS cập nhật: {cas_n} kênh")
    growth_n = refresh_growth_trends() if refresh_growth else 0
    if refresh_growth:
        logger.info(f"📈 Growth cập nhật: {growth_n} kênh")
    return {"cas_updated": cas_n, "growth_updated": growth_n}


# ── Pipeline xếp hạng & đề xuất ────────────────────────────────────────────────

def run_channel_pipeline(
    target_region: str,
    *,
    platform: Optional[str] = None,
    refresh_scores: bool = True,
    top_k_rank: int = 20,
    top_k_recommend: int = 10,
    min_cas: float = 20.0,
    min_rcas: float = 10.0,
    diverse: bool = True,
) -> dict:
    """
    [refresh] → [rank] → [recommend] cho một khu vực.
    Trả về: region, run_at, refresh_summary, ranking, recommendations
    """
    from database.channel_repository import rank_channels_in_region, recommend_channels_by_region

    logger.info(f"🚀 Channel Pipeline [{target_region}]")
    result: dict = {
        "region":          target_region,
        "run_at":          datetime.now(timezone.utc).isoformat(),
        "refresh_summary": None,
        "ranking":         [],
        "recommendations": [],
    }

    if refresh_scores:
        result["refresh_summary"] = refresh_channel_scores()

    result["ranking"] = rank_channels_in_region(
        target_region, platform=platform, min_cas=min_cas,
    )[:top_k_rank]

    result["recommendations"] = recommend_channels_by_region(
        target_region, platform=platform,
        top_k=top_k_recommend, min_cas=min_cas, min_rcas=min_rcas,
        diverse=diverse,
    )

    logger.info(f"✅ {len(result['ranking'])} xếp hạng | {len(result['recommendations'])} đề xuất")
    return result


# ── Export helpers ──────────────────────────────────────────────────────────────

_EXPORT_FIELDS = [
    "rank", "channel_name", "username", "platform", "country", "region_tag",
    "follower_count", "cas", "rcas", "tier", "channel_url",
    "broadcast_freq_weekly", "total_livestreams", "last_live_at",
]


def export_ranking(ranking: list[dict], fmt: str = "csv") -> str:
    """
    Chuyển đổi danh sách ranking thành CSV hoặc JSON string để download.

    Args:
        ranking: list[dict] trả về từ run_channel_pipeline()["ranking"]
        fmt:     "csv" | "json"

    Returns:
        str — nội dung file để ghi hoặc truyền vào st.download_button
    """
    rows = []
    for i, ch in enumerate(ranking, 1):
        row = {"rank": i}
        for f in _EXPORT_FIELDS[1:]:
            v = ch.get(f)
            if isinstance(v, float):
                v = round(v, 2)
            row[f] = v if v is not None else ""
        rows.append(row)

    if fmt == "json":
        return json.dumps(rows, ensure_ascii=False, indent=2)

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_EXPORT_FIELDS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()

