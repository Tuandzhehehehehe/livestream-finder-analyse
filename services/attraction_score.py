"""
services/attraction_score.py — Channel Attraction Score Engine
==============================================================
Tính điểm hấp dẫn kênh livestream theo 2 tầng:

  CAS  (Channel Attraction Score)  — chất lượng tuyệt đối [0–100]
  RCAS (Regional CAS)              — mức độ phù hợp với khu vực [0–100]

Tier: 80+ 🔥 Hot | 60+ ⭐ Promising | 40+ 📈 Growing | 20+ 💤 Passive | <20 ❌ Stale

Weights: audience=0.30 | activity=0.25 | engagement=0.25 | recency=0.15 | commerce=0.05
Regional relevance: location 0–0.6 | language 0–0.3 | content 0–0.1 | floor=0.1
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
    "VN": ["vietnam", "viet nam", "việt", "hà nội", "hanoi", "hcm", "sài gòn",
           "saigon", "đà nẵng", "danang", "hải phòng", "cần thơ", "việt nam"],
    "TH": ["thailand", "thai", "bangkok", "thái lan", "krung thep",
           "chiang mai", "phuket", "ประเทศไทย", "กรุงเทพ"],
    "SG": ["singapore", "sg", "singapura"],
    "MY": ["malaysia", "kuala lumpur", "kl", "penang", "johor", "sabah", "sarawak"],
    "ID": ["indonesia", "jakarta", "bali", "bandung", "surabaya", "yogyakarta",
           "medan", "makassar", "indo"],
    "PH": ["philippines", "manila", "cebu", "davao", "quezon", "pilipinas"],
    "MM": ["myanmar", "burma", "yangon", "mandalay", "naypyidaw", "မြန်မာ"],
    "KH": ["cambodia", "phnom penh", "siem reap", "ប្រទេសកម្ពុជា"],
    "LA": ["laos", "vientiane", "luang prabang", "ລາວ"],
    "CN": ["china", "beijing", "shanghai", "guangzhou", "shenzhen",
           "中国", "北京", "上海", "广州", "深圳"],
    "HK": ["hong kong", "hongkong", "香港"],
    "TW": ["taiwan", "taipei", "taichung", "kaohsiung", "台灣", "台北"],
    "JP": ["japan", "tokyo", "osaka", "kyoto", "日本", "東京", "大阪"],
    "KR": ["korea", "seoul", "busan", "한국", "서울", "부산"],
    "IN": ["india", "new delhi", "mumbai", "bangalore", "bengaluru",
           "hyderabad", "chennai", "kolkata", "भारत"],
    "US": ["usa", "united states", "new york", "los angeles", "san francisco",
           "chicago", "houston", "miami", "silicon valley"],
    "GB": ["uk", "united kingdom", "london", "manchester", "birmingham",
           "england", "scotland", "britain"],
    "AU": ["australia", "sydney", "melbourne", "brisbane", "perth"],
    "CA": ["canada", "toronto", "vancouver", "montreal", "calgary"],
    "DE": ["germany", "berlin", "munich", "hamburg", "deutschland"],
    "FR": ["france", "paris", "marseille", "lyon"],
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
    """
    Viewer-to-Follower Rate. Fallback platform-aware khi avg_viewers=None:
      youtube+history=3.0 | tiktok=2.0 | web=2.5 | unknown=1.5
    """
    avg = ch.get("avg_viewers")
    if avg is None:
        platform = (ch.get("platform") or "").lower()
        has_history = bool(ch.get("total_livestreams") or ch.get("activity_history"))
        if platform == "youtube" and has_history: return 3.0
        if platform == "tiktok":  return 2.0
        if platform == "web":     return 2.5
        return 1.5
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


_WEIGHTS = [
    (_audience,   0.30),
    (_activity,   0.25),
    (_engagement, 0.25),
    (_recency,    0.15),
    (_commerce,   0.05),
]


def compute_cas(channel: dict) -> float:
    """Tính CAS ∈ [0, 100]."""
    return round(_clamp(sum(fn(channel) * w for fn, w in _WEIGHTS) * 10, 0, 100), 2)


def cas_breakdown(channel: dict) -> dict:
    """Chi tiết điểm từng component."""
    rows = {fn.__name__.lstrip("_"): (fn(channel), w) for fn, w in _WEIGHTS}
    cas  = round(_clamp(sum(s * w for s, w in rows.values()) * 10, 0, 100), 2)
    return {
        "cas":  cas,
        "tier": cas_tier(cas),
        "components": {
            name: {"score_10": round(s, 3), "weighted": round(s * w, 3)}
            for name, (s, w) in rows.items()
        },
    }


def cas_explain(channel: dict) -> str:
    """Human-readable breakdown của CAS — dùng trực tiếp output của cas_breakdown."""
    bd = cas_breakdown(channel)
    lines = [f"CAS = {bd['cas']} {bd['tier']}"]
    for name, data in bd["components"].items():
        lines.append(f"  • {name:<12} score={data['score_10']:.2f}/10  weighted={data['weighted']:.3f}")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# TẦNG 2 — RCAS
# ══════════════════════════════════════════════════════════════════════════════

def _relevance_scores(channel: dict, target_region: str) -> tuple[float, float, float, list[str]]:
    """
    Tính (loc, lng, cont, matched_keywords) — shared logic cho cả
    _regional_relevance() và regional_relevance_breakdown().
    """
    target_country = target_region.split("-")[0].upper()
    region_tag = channel.get("region_tag") or ""
    country    = (channel.get("country") or "").upper()
    lang       = (channel.get("language") or "").lower()
    expected   = _REGION_LANGUAGES.get(target_country, ["en"])
    text       = ((channel.get("description") or "") + " " + (channel.get("channel_name") or "")).lower()
    keywords   = _REGION_KEYWORDS.get(target_country, [])
    matched    = [kw for kw in keywords if kw in text]

    if region_tag == target_region:
        loc = 0.6
    elif (region_tag.split("-")[0] or country) == target_country:
        loc = 0.4
    elif not region_tag and not country:
        loc = 0.1
    else:
        loc = 0.0

    if not lang:          lng = 0.1
    elif lang in expected: lng = 0.3
    elif lang == "en":    lng = 0.2
    else:                 lng = 0.0

    cont = 0.1 if matched else 0.0
    return loc, lng, cont, matched


def _regional_relevance(channel: dict, target_region: str) -> float:
    """Hệ số relevance [0.1, 1.0]."""
    loc, lng, cont, _ = _relevance_scores(channel, target_region)
    return max(loc + lng + cont, 0.1)


def regional_relevance_breakdown(channel: dict, target_region: str) -> dict:
    """Debug view của regional relevance."""
    loc, lng, cont, matched = _relevance_scores(channel, target_region)
    relevance = max(loc + lng + cont, 0.1)
    return {
        "relevance":       round(relevance, 3),
        "location_score":  loc,
        "language_score":  lng,
        "content_score":   cont,
        "matched_keywords": matched,
        "explanation":     f"loc={loc} + lang={lng} + content={cont} → {relevance:.3f}",
    }


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
    out = []
    for ch in channels:
        cas = float(ch.get("cas") or 0) or compute_cas(ch)
        if cas < min_cas:
            continue
        rcas = compute_rcas(cas, ch, target_region)
        if rcas < min_rcas:
            continue
        out.append({**ch, "cas": cas, "rcas": rcas, "tier": cas_tier(cas)})
    out.sort(
        key=lambda x: (x["rcas"], x["cas"], int(x.get("follower_count") or 0)),
        reverse=True,
    )
    return out[:top_k] if top_k else out


def rank_channels_by_region(
    channels: list[dict],
    target_region: str,
    *,
    min_cas: float = 0.0,
) -> list[dict]:
    """Xếp hạng kênh theo RCAS."""
    return _score_and_sort(channels, target_region, min_cas=min_cas, min_rcas=0.0)


def recommend_channels(
    channels: list[dict],
    target_region: str,
    *,
    top_k: int = 10,
    min_cas: float = 20.0,
    min_rcas: float = 10.0,
) -> list[dict]:
    """Đề xuất top K kênh phù hợp nhất với khu vực."""
    return _score_and_sort(channels, target_region, min_cas=min_cas, min_rcas=min_rcas, top_k=top_k)


def recommend_reason(channel: dict, target_region: str) -> str:
    """
    Trả về chuỗi ngắn giải thích tại sao kênh này được đề xuất cho khu vực.
    Dùng regional_relevance_breakdown() đã có sẵn.
    """
    bd = regional_relevance_breakdown(channel, target_region)
    parts: list[str] = []

    if bd["location_score"] >= 0.6:
        parts.append(f"📍 Cùng khu vực {target_region}")
    elif bd["location_score"] >= 0.4:
        parts.append(f"🌏 Cùng quốc gia {target_region.split('-')[0]}")

    if bd["language_score"] >= 0.3:
        parts.append(f"🗣️ Ngôn ngữ phù hợp ({(channel.get('language') or '').upper()})")
    elif bd["language_score"] >= 0.2:
        parts.append("🗣️ Dùng tiếng Anh (tiếp cận rộng)")

    if bd["matched_keywords"]:
        parts.append(f"🔑 Từ khóa khớp: {', '.join(bd['matched_keywords'][:3])}")

    tier = channel.get("tier", "")
    if "🔥" in tier:
        parts.append("🔥 Kênh đang rất hot")
    elif "⭐" in tier:
        parts.append("⭐ Kênh nhiều tiềm năng")

    return "  ·  ".join(parts) if parts else "📊 Điểm RCAS phù hợp với khu vực"


def recommend_channels_diverse(
    channels: list[dict],
    target_region: str,
    *,
    top_k: int = 10,
    min_cas: float = 20.0,
    min_rcas: float = 10.0,
) -> list[dict]:
    """
    Đề xuất top K kênh với platform-capped diversification.

    Mỗi platform tối đa ceil(top_k / 2) kênh trong kết quả.
    Nếu sau khi diversify vẫn chưa đủ top_k → fallback: bổ sung từ
    các kênh bị loại (relax cap) cho đến khi đủ hoặc hết.
    """
    per_platform_cap = math.ceil(top_k / 2)
    pool = _score_and_sort(channels, target_region, min_cas=min_cas, min_rcas=min_rcas)

    selected: list[dict] = []
    overflow: list[dict] = []
    platform_count: dict[str, int] = {}

    for ch in pool:
        plat = (ch.get("platform") or "unknown").lower()
        if platform_count.get(plat, 0) < per_platform_cap:
            platform_count[plat] = platform_count.get(plat, 0) + 1
            selected.append(ch)
            if len(selected) >= top_k:
                break
        else:
            overflow.append(ch)

    # Fallback: bổ sung từ overflow nếu chưa đủ
    for ch in overflow:
        if len(selected) >= top_k:
            break
        selected.append(ch)

    return selected

