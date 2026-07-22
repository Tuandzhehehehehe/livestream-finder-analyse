"""
channel_crawler/region_mapper.py — Location → Region Tag Normalizer
====================================================================
Chuẩn hoá chuỗi địa danh thô từ platform → region_tag theo chuẩn nội bộ.

Format region_tag: {COUNTRY_ISO2}-{CITY_CODE}
  VD: VN-HN, VN-HCM, VN-DN, TH-BKK, SG-SG, MY-KL, ID-JKT, PH-MNL, US, UK ...

Hỗ trợ:
  - Tiếng Việt có dấu / không dấu
  - Tiếng Anh
  - Tên quốc tế thông dụng trong khu vực Đông Nam Á + Global
"""

from __future__ import annotations

import unicodedata
import re
from typing import Optional

# ── Unicode normalisation ──────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Lowercase, strip dấu, bỏ ký tự đặc biệt → chuỗi ASCII thuần."""
    text = text.lower().strip()
    # Decompose unicode → remove combining marks (dấu tiếng Việt)
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text


# ── Mapping table ──────────────────────────────────────────────────────────────
# Key: normalized alias (lowercase, no dấu, stripped)
# Value: (country_iso2, region_tag)

_LOCATION_MAP: dict[str, tuple[str, str]] = {
    # ── Việt Nam ─────────────────────────────────────────────────────────────
    "viet nam":               ("VN", "VN"),
    "vietnam":                ("VN", "VN"),
    "vn":                     ("VN", "VN"),

    # Hà Nội
    "ha noi":                 ("VN", "VN-HN"),
    "hanoi":                  ("VN", "VN-HN"),
    "ha nội":                 ("VN", "VN-HN"),
    "hà nội":                 ("VN", "VN-HN"),
    "hn":                     ("VN", "VN-HN"),

    # TP. Hồ Chí Minh / Sài Gòn
    "ho chi minh":            ("VN", "VN-HCM"),
    "ho chi minh city":       ("VN", "VN-HCM"),
    "hcm":                    ("VN", "VN-HCM"),
    "hcmc":                   ("VN", "VN-HCM"),
    "saigon":                 ("VN", "VN-HCM"),
    "sai gon":                ("VN", "VN-HCM"),
    "tp hcm":                 ("VN", "VN-HCM"),
    "tp. hcm":                ("VN", "VN-HCM"),
    "thanh pho ho chi minh":  ("VN", "VN-HCM"),
    "tp ho chi minh":         ("VN", "VN-HCM"),

    # Đà Nẵng
    "da nang":                ("VN", "VN-DN"),
    "danang":                 ("VN", "VN-DN"),
    "đà nẵng":                ("VN", "VN-DN"),
    "da nẵng":                ("VN", "VN-DN"),

    # Hải Phòng
    "hai phong":              ("VN", "VN-HP"),
    "haiphong":               ("VN", "VN-HP"),

    # Cần Thơ
    "can tho":                ("VN", "VN-CT"),

    # Huế
    "hue":                    ("VN", "VN-HUE"),
    "thua thien hue":         ("VN", "VN-HUE"),

    # Bình Dương
    "binh duong":             ("VN", "VN-BD"),

    # Đồng Nai
    "dong nai":               ("VN", "VN-DN2"),

    # Bà Rịa - Vũng Tàu
    "vung tau":               ("VN", "VN-VT"),
    "ba ria":                 ("VN", "VN-VT"),

    # Nghệ An
    "nghe an":                ("VN", "VN-NA"),
    "vinh":                   ("VN", "VN-NA"),

    # Khánh Hoà
    "khanh hoa":              ("VN", "VN-KH"),
    "nha trang":              ("VN", "VN-KH"),

    # ── Thái Lan ─────────────────────────────────────────────────────────────
    "thailand":               ("TH", "TH"),
    "thai lan":               ("TH", "TH"),
    "th":                     ("TH", "TH"),
    "bangkok":                ("TH", "TH-BKK"),
    "krung thep":             ("TH", "TH-BKK"),
    "chiang mai":             ("TH", "TH-CNX"),
    "phuket":                 ("TH", "TH-HKT"),

    # ── Singapore ────────────────────────────────────────────────────────────
    "singapore":              ("SG", "SG"),
    "sg":                     ("SG", "SG"),

    # ── Malaysia ─────────────────────────────────────────────────────────────
    "malaysia":               ("MY", "MY"),
    "my":                     ("MY", "MY"),
    "kuala lumpur":           ("MY", "MY-KL"),
    "kl":                     ("MY", "MY-KL"),
    "penang":                 ("MY", "MY-PNG"),
    "johor":                  ("MY", "MY-JHR"),
    "johor bahru":            ("MY", "MY-JHR"),

    # ── Indonesia ────────────────────────────────────────────────────────────
    "indonesia":              ("ID", "ID"),
    "id":                     ("ID", "ID"),
    "jakarta":                ("ID", "ID-JKT"),
    "bandung":                ("ID", "ID-BDG"),
    "surabaya":               ("ID", "ID-SUB"),
    "bali":                   ("ID", "ID-DPS"),
    "yogyakarta":             ("ID", "ID-JOG"),

    # ── Philippines ──────────────────────────────────────────────────────────
    "philippines":            ("PH", "PH"),
    "ph":                     ("PH", "PH"),
    "manila":                 ("PH", "PH-MNL"),
    "metro manila":           ("PH", "PH-MNL"),
    "cebu":                   ("PH", "PH-CEB"),
    "davao":                  ("PH", "PH-DVO"),

    # ── Myanmar ──────────────────────────────────────────────────────────────
    "myanmar":                ("MM", "MM"),
    "burma":                  ("MM", "MM"),
    "yangon":                 ("MM", "MM-RGN"),
    "naypyidaw":              ("MM", "MM-NPT"),

    # ── Campuchia ────────────────────────────────────────────────────────────
    "cambodia":               ("KH", "KH"),
    "phnom penh":             ("KH", "KH-PNH"),

    # ── Lào ──────────────────────────────────────────────────────────────────
    "laos":                   ("LA", "LA"),
    "vientiane":              ("LA", "LA-VTE"),

    # ── Trung Quốc ───────────────────────────────────────────────────────────
    "china":                  ("CN", "CN"),
    "beijing":                ("CN", "CN-BJ"),
    "shanghai":               ("CN", "CN-SH"),
    "guangzhou":              ("CN", "CN-GZ"),
    "shenzhen":               ("CN", "CN-SZ"),
    "hong kong":              ("HK", "HK"),
    "taiwan":                 ("TW", "TW"),
    "taipei":                 ("TW", "TW-TPE"),

    # ── Nhật Bản ─────────────────────────────────────────────────────────────
    "japan":                  ("JP", "JP"),
    "tokyo":                  ("JP", "JP-TKY"),
    "osaka":                  ("JP", "JP-OSK"),

    # ── Hàn Quốc ─────────────────────────────────────────────────────────────
    "south korea":            ("KR", "KR"),
    "korea":                  ("KR", "KR"),
    "seoul":                  ("KR", "KR-SEL"),

    # ── Ấn Độ ────────────────────────────────────────────────────────────────
    "india":                  ("IN", "IN"),
    "new delhi":              ("IN", "IN-DEL"),
    "mumbai":                 ("IN", "IN-BOM"),
    "bangalore":              ("IN", "IN-BLR"),
    "bengaluru":              ("IN", "IN-BLR"),

    # ── Mỹ ───────────────────────────────────────────────────────────────────
    "united states":          ("US", "US"),
    "usa":                    ("US", "US"),
    "us":                     ("US", "US"),
    "new york":               ("US", "US-NYC"),
    "los angeles":            ("US", "US-LAX"),
    "san francisco":          ("US", "US-SFO"),

    # ── Anh ──────────────────────────────────────────────────────────────────
    "united kingdom":         ("GB", "GB"),
    "uk":                     ("GB", "GB"),
    "london":                 ("GB", "GB-LON"),

    # ── Úc ───────────────────────────────────────────────────────────────────
    "australia":              ("AU", "AU"),
    "sydney":                 ("AU", "AU-SYD"),
    "melbourne":              ("AU", "AU-MEL"),

    # ── Canada ───────────────────────────────────────────────────────────────
    "canada":                 ("CA", "CA"),
    "toronto":                ("CA", "CA-YYZ"),
    "vancouver":              ("CA", "CA-YVR"),

    # ── Đức ──────────────────────────────────────────────────────────────────
    "germany":                ("DE", "DE"),
    "berlin":                 ("DE", "DE-BER"),

    # ── Pháp ─────────────────────────────────────────────────────────────────
    "france":                 ("FR", "FR"),
    "paris":                  ("FR", "FR-PAR"),
}

# Pre-compute normalized keys for lookup
_NORMALIZED_MAP: dict[str, tuple[str, str]] = {
    _normalize(k): v for k, v in _LOCATION_MAP.items()
}


def map_location(location_raw: Optional[str]) -> dict:
    """
    Chuyển đổi chuỗi địa danh thô sang thông tin khu vực chuẩn.

    Args:
        location_raw: Chuỗi địa danh từ platform (VD: "Hà Nội, Việt Nam")

    Returns:
        {
            "country":    "VN",
            "region_tag": "VN-HN",
            "matched":    True,
        }

    Logic:
        1. Exact match trên toàn chuỗi
        2. Split theo dấu phẩy/dấu gạch — thử từng phần độc lập,
           chọn kết quả có region_tag cụ thể nhất (có dash "-" được ưu tiên)
        3. Substring match dài nhất trên toàn chuỗi
    """
    if not location_raw:
        return {"country": None, "region_tag": None, "matched": False}

    normalized = _normalize(location_raw)

    # 1. Exact match
    if normalized in _NORMALIZED_MAP:
        country, region_tag = _NORMALIZED_MAP[normalized]
        return {"country": country, "region_tag": region_tag, "matched": True}

    # Helper: tìm best substring match trong một chuỗi đã normalize
    def _best_match(s: str) -> Optional[tuple[str, str]]:
        best_key   = None
        best_score = 0
        for key in _NORMALIZED_MAP:
            if key in s:
                score = len(key)
                if score > best_score:
                    best_key   = key
                    best_score = score
        return _NORMALIZED_MAP[best_key] if best_key else None

    # 2. Split theo dấu phẩy — thử từng phần
    # "Hà Nội, Việt Nam" → ["ha noi", "viet nam"]
    # Ưu tiên phần có region_tag cụ thể hơn (có dấu "-")
    parts = [p.strip() for p in re.split(r"[,/|;]", normalized) if p.strip()]
    if len(parts) > 1:
        candidates = []
        for part in parts:
            match = _best_match(part)
            if match:
                candidates.append(match)
        if candidates:
            # Ưu tiên region_tag có dấu "-" (cụ thể hơn) → nếu bằng nhau thì lấy cái đầu
            candidates.sort(key=lambda x: (0 if "-" in x[1] else 1, -len(x[1])))
            country, region_tag = candidates[0]
            return {"country": country, "region_tag": region_tag, "matched": True}

    # 3. Substring match dài nhất trên toàn chuỗi
    match = _best_match(normalized)
    if match:
        country, region_tag = match
        return {"country": country, "region_tag": region_tag, "matched": True}

    return {"country": None, "region_tag": None, "matched": False}


def enrich_channel_with_region(channel_data: dict) -> dict:
    """
    Thêm trường country và region_tag vào channel_data dict
    dựa trên location_raw (in-place + return).
    """
    region_info = map_location(channel_data.get("location_raw"))
    if not channel_data.get("country"):
        channel_data["country"]    = region_info["country"]
    if not channel_data.get("region_tag"):
        channel_data["region_tag"] = region_info["region_tag"]
    return channel_data


# ── Utilities ─────────────────────────────────────────────────────────────────

def list_supported_regions() -> list[str]:
    """Trả về danh sách tất cả region_tag được hỗ trợ."""
    return sorted({v[1] for v in _LOCATION_MAP.values()})


def list_supported_countries() -> list[str]:
    """Trả về danh sách tất cả country code được hỗ trợ."""
    return sorted({v[0] for v in _LOCATION_MAP.values()})
