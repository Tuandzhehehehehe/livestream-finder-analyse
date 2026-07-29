"""
database/channel_repository.py — Channel Info Data Access Layer
================================================================
Tất cả thao tác với channel_info.db đều đi qua đây.
Import engine và tables từ database.db (cùng hệ thống schema).
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

# pyrefly: ignore [missing-import]
from sqlalchemy import select, update, delete, func as sqlfunc
# pyrefly: ignore [missing-import]
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from database.db import channel_engine as engine, channel_profiles, follower_snapshots
from services.attraction_score import (
    compute_cas, rank_channels_by_region, recommend_channels,
)


# ── Write operations ──────────────────────────────────────────────────────────

def upsert_channel(data: dict) -> bool:
    """
    Thêm mới hoặc cập nhật thông tin kênh.

    data phải có ít nhất:
        platform, channel_id, channel_url

    Trả về True nếu thành công.
    """
    required = ("platform", "channel_id", "channel_url")
    if not all(data.get(k) for k in required):
        missing = [k for k in required if not data.get(k)]
        raise ValueError(f"upsert_channel: thiếu trường bắt buộc: {missing}")

    row = {
        "platform":              data.get("platform"),
        "channel_id":            data.get("channel_id"),
        "channel_url":           data.get("channel_url"),
        "username":              data.get("username"),
        "channel_name":          data.get("channel_name"),
        "follower_count":        data.get("follower_count", 0),
        "growth_7d_pct":         data.get("growth_7d_pct"),
        "growth_30d_pct":        data.get("growth_30d_pct"),
        "total_livestreams":     data.get("total_livestreams", 0),
        "broadcast_freq_weekly": data.get("broadcast_freq_weekly"),
        "last_live_at":          data.get("last_live_at"),
        "avg_viewers":           data.get("avg_viewers"),
        "category":              data.get("category"),
        "language":              data.get("language"),
        "description":           data.get("description"),
        "is_verified":           int(bool(data.get("is_verified", False))),
        "location_raw":          data.get("location_raw"),
        "country":               data.get("country"),
        "region_tag":            data.get("region_tag"),
        "timezone":              data.get("timezone"),
        "seller_info":           data.get("seller_info"),
        "activity_history":      data.get("activity_history"),
        "channel_created_at":    data.get("channel_created_at"),
        "cas":                   data.get("cas"),
        "cas_computed_at":       data.get("cas_computed_at"),
    }

    try:
        with engine.begin() as conn:
            stmt = (
                sqlite_insert(channel_profiles)
                .values(**row)
                .on_conflict_do_update(
                    index_elements=["channel_url"],
                    set_={k: v for k, v in row.items() if k != "channel_url"},
                )
            )
            conn.execute(stmt)

        # Tự động lưu snapshot follower
        if data.get("follower_count") is not None:
            save_follower_snapshot(
                channel_url=data["channel_url"],
                platform=data["platform"],
                follower_count=int(data["follower_count"]),
            )
        return True
    except Exception as e:
        print(f"[ChannelRepo] upsert_channel error: {e}")
        return False


def save_follower_snapshot(channel_url: str, platform: str, follower_count: int) -> bool:
    """
    Lưu một điểm follower count vào bảng follower_snapshots.
    Bỏ qua nếu đã có bản ghi trong vòng 6 giờ gần nhất (tránh duplicate).
    """
    try:
        with engine.begin() as conn:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
            recent = conn.execute(
                select(follower_snapshots.c.id)
                .where(follower_snapshots.c.channel_url == channel_url)
                .where(follower_snapshots.c.snapped_at >= cutoff)
                .limit(1)
            ).fetchone()

            if recent:
                return False  # bỏ qua, quá gần lần trước

            conn.execute(
                follower_snapshots.insert().values(
                    channel_url=channel_url,
                    platform=platform,
                    follower_count=follower_count,
                )
            )
        return True
    except Exception as e:
        print(f"[ChannelRepo] save_follower_snapshot error: {e}")
        return False


# ── Read operations ───────────────────────────────────────────────────────────

def get_channel_by_url(channel_url: str) -> Optional[dict]:
    """Lấy thông tin kênh theo URL. Trả về dict hoặc None."""
    with engine.connect() as conn:
        row = conn.execute(
            select(channel_profiles).where(channel_profiles.c.channel_url == channel_url)
        ).fetchone()
    return dict(row._mapping) if row else None


def get_channel_by_id(platform: str, channel_id: str) -> Optional[dict]:
    """Lấy thông tin kênh theo (platform, channel_id)."""
    with engine.connect() as conn:
        row = conn.execute(
            select(channel_profiles)
            .where(channel_profiles.c.platform == platform)
            .where(channel_profiles.c.channel_id == channel_id)
        ).fetchone()
    return dict(row._mapping) if row else None


def get_all_channels(platform: Optional[str] = None) -> list[dict]:
    """
    Lấy tất cả kênh, tuỳ chọn lọc theo platform.
    Trả về list of dict, sắp xếp giảm dần theo follower_count.
    """
    with engine.connect() as conn:
        stmt = select(channel_profiles)
        if platform:
            stmt = stmt.where(channel_profiles.c.platform == platform.lower())
        stmt = stmt.order_by(channel_profiles.c.follower_count.desc())
        rows = conn.execute(stmt).fetchall()
    return [dict(r._mapping) for r in rows]


def get_channels_by_region(region_tag: str, platform: Optional[str] = None) -> list[dict]:
    """
    Lấy danh sách kênh theo region_tag (VD: 'VN-HN', 'VN-HCM', 'TH-BKK').
    Hỗ trợ prefix match: 'VN' sẽ khớp 'VN-HN', 'VN-HCM', ...
    Kết quả sắp xếp giảm dần theo follower_count.
    """
    with engine.connect() as conn:
        stmt = select(channel_profiles).where(
            channel_profiles.c.region_tag.like(f"{region_tag}%")
        )
        if platform:
            stmt = stmt.where(channel_profiles.c.platform == platform.lower())
        stmt = stmt.order_by(channel_profiles.c.follower_count.desc())
        rows = conn.execute(stmt).fetchall()
    return [dict(r._mapping) for r in rows]


def get_channels_by_country(country: str) -> list[dict]:
    """Lấy danh sách kênh theo mã quốc gia (VD: 'VN', 'TH', 'US')."""
    with engine.connect() as conn:
        rows = conn.execute(
            select(channel_profiles)
            .where(channel_profiles.c.country == country.upper())
            .order_by(channel_profiles.c.follower_count.desc())
        ).fetchall()
    return [dict(r._mapping) for r in rows]


def get_follower_snapshots(channel_url: str, days: int = 30) -> list[dict]:
    """Lấy lịch sử follower trong N ngày gần nhất."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with engine.connect() as conn:
        rows = conn.execute(
            select(follower_snapshots)
            .where(follower_snapshots.c.channel_url == channel_url)
            .where(follower_snapshots.c.snapped_at >= cutoff)
            .order_by(follower_snapshots.c.snapped_at.asc())
        ).fetchall()
    return [dict(r._mapping) for r in rows]


# ── Analytics ─────────────────────────────────────────────────────────────────

def compute_growth_trend(channel_url: str) -> dict:
    """
    Tính % tăng trưởng follower dựa trên dữ liệu lịch sử snapshots.

    Returns:
        {
            "growth_7d_pct":  float | None,
            "growth_30d_pct": float | None,
            "snapshots_used": int,
        }
    """
    now = datetime.now(timezone.utc)

    def _nearest_snapshot_before(days: int) -> Optional[int]:
        target = now - timedelta(days=days)
        with engine.connect() as conn:
            row = conn.execute(
                select(follower_snapshots.c.follower_count)
                .where(follower_snapshots.c.channel_url == channel_url)
                .where(follower_snapshots.c.snapped_at >= target - timedelta(hours=48))
                .where(follower_snapshots.c.snapped_at <= target + timedelta(hours=48))
                .order_by(
                    sqlfunc.abs(
                        sqlfunc.julianday(follower_snapshots.c.snapped_at)
                        - sqlfunc.julianday(target.isoformat())
                    )
                )
                .limit(1)
            ).fetchone()
        return row[0] if row else None

    snapshots = get_follower_snapshots(channel_url, days=30)
    if not snapshots:
        return {"growth_7d_pct": None, "growth_30d_pct": None, "snapshots_used": 0}

    current = snapshots[-1]["follower_count"]
    result  = {"growth_7d_pct": None, "growth_30d_pct": None, "snapshots_used": len(snapshots)}

    def _pct(old: Optional[int]) -> Optional[float]:
        if old is None or old == 0:
            return None
        return round((current - old) / old * 100, 2)

    result["growth_7d_pct"]  = _pct(_nearest_snapshot_before(7))
    result["growth_30d_pct"] = _pct(_nearest_snapshot_before(30))
    return result


# ── CAS Scoring ─────────────────────────────────────────────────────────────────────

def update_channel_cas(channel_url: str) -> Optional[float]:
    """
    Tính lại CAS cho một kênh và ghi vào DB.

    Returns:
        float CAS mới, hoặc None nếu kênh không tồn tại.
    """
    ch = get_channel_by_url(channel_url)
    if not ch:
        return None
    cas = compute_cas(ch)
    try:
        with engine.begin() as conn:
            conn.execute(
                update(channel_profiles)
                .where(channel_profiles.c.channel_url == channel_url)
                .values(cas=cas, cas_computed_at=datetime.now(timezone.utc))
            )
        return cas
    except Exception as e:
        print(f"[ChannelRepo] update_channel_cas error ({channel_url}): {e}")
        return None


def refresh_all_cas() -> int:
    """
    Tính lại CAS cho tất cả kênh và ghi vào DB.

    Returns:
        Số kênh đã cập nhật.
    """
    updated = 0
    for ch in get_all_channels():
        cas = compute_cas(ch)
        try:
            with engine.begin() as conn:
                conn.execute(
                    update(channel_profiles)
                    .where(channel_profiles.c.channel_url == ch["channel_url"])
                    .values(cas=cas, cas_computed_at=datetime.now(timezone.utc))
                )
            updated += 1
        except Exception as e:
            print(f"[ChannelRepo] refresh_all_cas error ({ch['channel_url']}): {e}")
    return updated


# ── Regional Ranking & Recommendation ─────────────────────────────────────────────

def rank_channels_in_region(
    target_region: str,
    platform: Optional[str] = None,
    min_cas: float = 0.0,
) -> list[dict]:
    """
    Xếp hạng kênh nổi bật trong một khu vực theo RCAS.

    Lấy kênh trong khu vực (prefix match region_tag), rồi xếp theo RCAS.

    Args:
        target_region: region_tag cần xếp hạng (VD: "VN-HCM", "VN", "TH-BKK")
        platform:      lọc theo platform nếu cần
        min_cas:       bỏ qua kênh có CAS dưới ngưỡng

    Returns:
        list[dict] với trường "cas" và "rcas" đã được thêm, sắp xếp giảm dần theo rcas.
    """
    channels = get_channels_by_region(target_region, platform=platform)
    return rank_channels_by_region(channels, target_region, min_cas=min_cas)


def recommend_channels_by_region(
    target_region: str,
    platform: Optional[str] = None,
    top_k: int = 10,
    min_cas: float = 20.0,
    min_rcas: float = 10.0,
) -> list[dict]:
    """
    Đề xuất kênh nổi bật cho một khu vực — không filter region cứng.

    Lấy toàn bộ kênh (kể cả global), tính RCAS cho từng kênh và trả top K.
    Kênh global CAS cao vẫn có thể được đề xuất nếu phù hợp (VD: kênh EN cho "SG").

    Args:
        target_region: region_tag mục tiêu (VD: "VN-HCM", "SG")
        platform:      lọc theo platform nếu cần
        top_k:         số lượng kênh đề xuất
        min_cas:       chỉ xem xét kênh có CAS >= min_cas
        min_rcas:      chỉ đề xuất kênh có RCAS >= min_rcas

    Returns:
        list[dict] top K kênh với trường "cas", "rcas", "tier".
    """
    channels = get_all_channels(platform=platform)
    return recommend_channels(
        channels, target_region,
        top_k=top_k, min_cas=min_cas, min_rcas=min_rcas,
    )


def refresh_growth_trends() -> int:
    """
    Tính lại growth_trend cho tất cả kênh và ghi vào channel_profiles.
    Trả về số kênh đã cập nhật.
    """
    updated = 0
    for ch in get_all_channels():
        trends = compute_growth_trend(ch["channel_url"])
        if trends["snapshots_used"] < 2:
            continue
        try:
            with engine.begin() as conn:
                conn.execute(
                    update(channel_profiles)
                    .where(channel_profiles.c.channel_url == ch["channel_url"])
                    .values(
                        growth_7d_pct=trends["growth_7d_pct"],
                        growth_30d_pct=trends["growth_30d_pct"],
                    )
                )
            updated += 1
        except Exception as e:
            print(f"[ChannelRepo] refresh_growth_trends error ({ch['channel_url']}): {e}")
    return updated


# ── Delete ────────────────────────────────────────────────────────────────────

def delete_channel(channel_url: str) -> bool:
    """Xoá kênh và toàn bộ snapshot của kênh đó."""
    try:
        with engine.begin() as conn:
            conn.execute(
                delete(follower_snapshots).where(follower_snapshots.c.channel_url == channel_url)
            )
            res = conn.execute(
                delete(channel_profiles).where(channel_profiles.c.channel_url == channel_url)
            )
        return res.rowcount > 0
    except Exception as e:
        print(f"[ChannelRepo] delete_channel error: {e}")
        return False
