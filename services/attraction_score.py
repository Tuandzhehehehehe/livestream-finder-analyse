"""
services/attraction_score.py — Channel Attraction Score Engine
==============================================================
Tính điểm hấp dẫn kênh livestream theo 2 tầng:

  CAS  (Channel Attraction Score)  — chất lượng tuyệt đối [0–100]
       Stateless, region-agnostic. Lưu vào DB.

  RCAS (Regional CAS)              — mức độ phù hợp với khu vực [0–100]
       Tính tại query time dựa trên target_region.

Tier: 80+ 🔥 Hot | 60+ ⭐ Promising | 40+ 📈 Growing | 20+ 💤 Passive | <20 ❌ Stale
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional


# ── Regional context ───────────────────────────────────────────────────────────

_REGION_LANGUAGES: dict[str, list[str]] = {
    "VN": ["vi"],       "TH": ["th"],        "SG": ["en", "zh", "ms"],
    "MY": ["ms", "en", "zh"], "ID": ["id"], "PH": ["fil", "en", "tl"],
    "MM": ["my"],       "KH": ["km"],        "LA": ["lo"],
    "CN": ["zh"],       "HK": ["zh", "en"],  "TW": ["zh"],
    "JP": ["ja"],       "KR": ["ko"],        "IN": ["hi", "en"],
    "US": ["en"],       "GB": ["en"],        "AU": ["en"],
    "CA": ["en", "fr"], "DE": ["de"],        "FR": ["fr"],
}

_REGION_KEYWORDS: dict[str, list[str]] = {
    "VN": ["vietnam", "viet nam", "việt", "hà nội", "hanoi", "hcm", "sài gòn", "saigon"],
    "TH": ["thailand", "thai", "bangkok", "thái lan"],
    "SG": ["singapore", "sg"],
    "MY": ["malaysia", "kuala lumpur", "kl"],
    "ID": ["indonesia", "jakarta", "bali"],
    "PH": ["philippines", "manila"],
    "MM": ["myanmar", "yangon"],
    "KH": ["cambodia", "phnom penh"],
    "JP": ["japan", "tokyo"],
    "KR": ["korea", "seoul"],
    "CN": ["china", "beijing", "shanghai"],
    "US": ["usa", "united states"],
    "GB": ["uk", "london"],
    "AU": ["australia", "sydney"],
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _days_since(iso_str: Optional[str]) -> Optional[int]:
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - dt).days)
    except Exception:
        return None


def cas_tier(cas: float) -> str:
    if cas >= 80: return "🔥 Hot"
    if cas >= 60: return "⭐ Promising"
    if cas >= 40: return "📈 Growing"
    if cas >= 20: return "💤 Passive"
    return "❌ Stale"


# ══════════════════════════════════════════════════════════════════════════════
# TẦNG 1 — CAS
# ══════════════════════════════════════════════════════════════════════════════

def _audience(ch: dict) -> float:
    """Quy mô (log scale) + tăng trưởng follower."""
    followers = int(ch.get("follower_count") or 0)
    f = _clamp(math.log10(followers + 1) / math.log10(10_000_000) * 6, 0, 6) if followers else 0.0

    g7, g30 = ch.get("growth_7d_pct"), ch.get("growth_30d_pct")
    g = (_clamp(float(g7)  / 5.0,  0, 4) if g7  is not None else
         _clamp(float(g30) / 10.0, 0, 2) if g30 is not None else 0.0)

    return _clamp(f + g, 0, 10)


def _activity(ch: dict) -> float:
    """Tần suất (70%) + tổng số buổi (30%)."""
    freq  = ch.get("broadcast_freq_weekly")
    total = int(ch.get("total_livestreams") or 0)
    freq_s = _clamp(float(freq) / 3.0 * 10, 0, 10) if freq else 0.0
    vol_s  = _clamp(math.log(total + 1) / math.log(100) * 10, 0, 10) if total else 0.0
    return freq_s * 0.7 + vol_s * 0.3


def _engagement(ch: dict) -> float:
    """Viewer-to-Follower Rate. Missing → neutral 3.0 (không phạt lỗi scraping)."""
    avg = ch.get("avg_viewers")
    if avg is None:
        return 3.0
    return _clamp(int(avg) / max(int(ch.get("follower_count") or 1), 1) / 0.02 * 10, 0, 10)


def _recency(ch: dict) -> float:
    """Step-decay theo số ngày kể từ buổi live gần nhất."""
    days = _days_since(ch.get("last_live_at"))
    if days is None: return 0.0
    if days <=  7:   return 10.0
    if days <= 14:   return 8.0
    if days <= 30:   return 6.0
    if days <= 60:   return 4.0
    if days <= 90:   return 2.0
    return 0.0


def _commerce(ch: dict) -> float:
    """Tín hiệu thương mại — bonus flags."""
    s = ch.get("seller_info") or {}
    return _clamp(
        4 * bool(s.get("is_seller"))
        + 3 * bool(ch.get("is_verified"))
        + 2 * bool(s.get("shop_url"))
        + 1 * bool(s.get("contact_email")),
        0, 10,
    )


# (fn, weight) — tổng weight = 1.0
_WEIGHTS = [
    (_audience,   0.30),
    (_activity,   0.25),
    (_engagement, 0.25),
    (_recency,    0.15),
    (_commerce,   0.05),
]


def compute_cas(channel: dict) -> float:
    """Tính CAS ∈ [0, 100]. Stateless, có thể tính từ bất kỳ channel dict nào."""
    return round(_clamp(sum(fn(channel) * w for fn, w in _WEIGHTS) * 10, 0, 100), 2)


def cas_breakdown(channel: dict) -> dict:
    """Chi tiết điểm từng component — dùng để debug / dashboard."""
    components = {fn.__name__.lstrip("_"): (fn(channel), w) for fn, w in _WEIGHTS}
    cas = round(_clamp(sum(s * w for s, w in components.values()) * 10, 0, 100), 2)
    return {
        "cas":  cas,
        "tier": cas_tier(cas),
        "components": {
            name: {"score_10": round(s, 3), "weighted": round(s * w, 3)}
            for name, (s, w) in components.items()
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# TẦNG 2 — RCAS
# ══════════════════════════════════════════════════════════════════════════════

def _regional_relevance(channel: dict, target_region: str) -> float:
    """
    Hệ số relevance [0.1, 1.0] = location (0–0.6) + language (0–0.3) + content (0–0.1).
    Floor 0.1 đảm bảo kênh global CAS cao vẫn xuất hiện trong recommend.
    """
    target_country = target_region.split("-")[0].upper()
    region_tag = channel.get("region_tag") or ""
    country    = (channel.get("country") or "").upper()

    # Location
    if region_tag == target_region:
        loc = 0.6
    elif (region_tag.split("-")[0] or country) == target_country:
        loc = 0.4
    elif not region_tag and not country:
        loc = 0.1   # unknown — không phạt cứng
    else:
        loc = 0.0

    # Language
    lang     = (channel.get("language") or "").lower()
    expected = _REGION_LANGUAGES.get(target_country, ["en"])
    if not lang:          lng = 0.1
    elif lang in expected: lng = 0.3
    elif lang == "en":    lng = 0.2   # EN partial value
    else:                 lng = 0.0

    # Content bonus
    text     = ((channel.get("description") or "") + " " + (channel.get("channel_name") or "")).lower()
    keywords = _REGION_KEYWORDS.get(target_country, [])
    cont     = 0.1 if keywords and any(kw in text for kw in keywords) else 0.0

    return max(loc + lng + cont, 0.1)


def compute_rcas(cas: float, channel: dict, target_region: str) -> float:
    """RCAS = CAS × regional_relevance ∈ [0, 100]."""
    return round(_clamp(cas * _regional_relevance(channel, target_region), 0, 100), 2)


# ══════════════════════════════════════════════════════════════════════════════
# High-level API
# ══════════════════════════════════════════════════════════════════════════════

def _score_and_sort(
    channels: list[dict],
    target_region: str,
    min_cas: float,
    min_rcas: float,
    top_k: Optional[int] = None,
) -> list[dict]:
    """Shared core: tính CAS+RCAS, lọc, sắp xếp, cắt top K."""
    out = []
    for ch in channels:
        cas = float(ch.get("cas") or 0) or compute_cas(ch)
        if cas < min_cas:
            continue
        rcas = compute_rcas(cas, ch, target_region)
        if rcas < min_rcas:
            continue
        out.append({**ch, "cas": cas, "rcas": rcas, "tier": cas_tier(cas)})
    out.sort(key=lambda x: x["rcas"], reverse=True)
    return out[:top_k] if top_k else out


def rank_channels_by_region(
    channels: list[dict],
    target_region: str,
    *,
    min_cas: float = 0.0,
) -> list[dict]:
    """Xếp hạng kênh (đã pre-filter theo region) theo RCAS."""
    return _score_and_sort(channels, target_region, min_cas=min_cas, min_rcas=0.0)


def recommend_channels(
    channels: list[dict],
    target_region: str,
    *,
    top_k: int = 10,
    min_cas: float = 20.0,
    min_rcas: float = 10.0,
) -> list[dict]:
    """Đề xuất top K kênh phù hợp nhất với khu vực từ toàn bộ danh sách."""
    return _score_and_sort(channels, target_region, min_cas=min_cas, min_rcas=min_rcas, top_k=top_k)
