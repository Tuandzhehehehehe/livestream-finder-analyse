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

import importlib
import logging
import os
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

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
}


def _get_crawl_fn(platform: str):
    dotpath = _CRAWLERS.get(platform.lower())
    if not dotpath:
        raise ValueError(f"Platform không hỗ trợ: '{platform}'. Dùng: {list(_CRAWLERS)}")
    mod_path, fn_name = dotpath.rsplit(".", 1)
    return getattr(importlib.import_module(mod_path), fn_name)


# ── Crawl + lưu DB ─────────────────────────────────────────────────────────────

def crawl_and_save_channels(urls: list[str], platform: str, *, max_live_history: int = 20) -> dict:
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
        ch["cas"] = compute_cas(ch)
        ch["cas_computed_at"] = datetime.now(timezone.utc).isoformat()
        ch["tier"] = cas_tier(ch["cas"])
        if upsert_channel(ch):
            saved.append(ch)
            logger.info(f"  ✔ {ch.get('channel_name', ch.get('channel_url', '?'))[:50]} | CAS={ch['cas']}")
        else:
            logger.warning(f"  ✘ Lưu thất bại: {ch.get('channel_url', '?')}")

    skipped += len(urls) - len(raw)
    logger.info(f"[{platform.upper()}] Hoàn tất: {len(saved)} lưu | {skipped} bỏ qua")
    return {"crawled": len(urls), "saved": len(saved), "skipped": skipped, "channels": saved}


# ── Auto-crawl channel từ livestream events ────────────────────────────────────

def _infer_channel_url(event_url: str, platform: str) -> str:
    """Suy luận channel URL từ URL của một livestream event."""
    if not event_url:
        return ""
    p = urlparse(event_url)
    path_parts = [s for s in p.path.split("/") if s]

    if platform == "youtube":
        path = p.path.rstrip("/")
        if "/channel/" in path or path.startswith("/@"):
            return f"https://youtube.com{path}"
        return ""  # watch?v= không suy luận được

    if platform == "tiktok" and path_parts and path_parts[0].startswith("@"):
        return f"https://tiktok.com/{path_parts[0]}"

    return ""


def enqueue_channels_from_events(events: list[dict]) -> dict:
    """
    Trích channel URL từ events, bỏ qua URL đã có trong DB, crawl batch mới.
    Trả về: {new_urls, skipped_existing, saved, skipped_crawl}
    """
    from database.channel_repository import get_channel_by_url

    # Trích và dedup channel URL theo platform
    platform_urls: dict[str, list[str]] = {}
    for ev in events:
        platform = (ev.get("platform") or "").lower()
        if not platform:
            continue
        ch_url = ev.get("channel_url", "").strip() or _infer_channel_url(ev.get("url", ""), platform)
        if ch_url and ch_url not in platform_urls.get(platform, []):
            platform_urls.setdefault(platform, []).append(ch_url)

    total_new = sum(len(v) for v in platform_urls.values())
    if not total_new:
        return {"new_urls": 0, "skipped_existing": 0, "saved": 0, "skipped_crawl": 0}

    # Lọc URL chưa có trong DB
    skipped_existing = 0
    to_crawl: dict[str, list[str]] = {}
    for platform, urls in platform_urls.items():
        fresh = [u for u in urls if not get_channel_by_url(u)]
        skipped_existing += len(urls) - len(fresh)
        if fresh:
            to_crawl[platform] = fresh

    if not to_crawl:
        logger.info(f"[AutoChannel] {skipped_existing} channel đã có trong DB")
        return {"new_urls": total_new, "skipped_existing": skipped_existing, "saved": 0, "skipped_crawl": 0}

    # Crawl batch theo platform
    saved = skipped_crawl = 0
    for platform, urls in to_crawl.items():
        try:
            s = crawl_and_save_channels(urls, platform)
            saved += s["saved"]
            skipped_crawl += s["skipped"]
        except Exception as e:
            logger.warning(f"[AutoChannel] {platform}: {e}")
            skipped_crawl += len(urls)

    logger.info(f"[AutoChannel] {saved} lưu | {skipped_existing} đã có | {skipped_crawl} lỗi")
    return {"new_urls": total_new, "skipped_existing": skipped_existing, "saved": saved, "skipped_crawl": skipped_crawl}


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
    )

    logger.info(f"✅ {len(result['ranking'])} xếp hạng | {len(result['recommendations'])} đề xuất")
    return result
