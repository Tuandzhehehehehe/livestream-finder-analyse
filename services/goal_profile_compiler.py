"""
Goal Profile Compiler
---------------------
Chuyển đổi ngôn ngữ người dùng (goal) thành một file JSON có cấu trúc
để AI model có thể đọc và xử lý mà không cần gọi AI nhiều lần.

Cách hoạt động:
- Lần đầu: gọi AI 1 lần duy nhất để compile -> lưu file JSON theo hash của goal
- Lần 2+: đọc trực tiếp từ file JSON, không tốn token
"""

import os
import json
import hashlib
import time

PROFILES_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "profiles")
)


def _goal_hash(goal: str) -> str:
    """Tạo hash ngắn từ goal để đặt tên file."""
    return hashlib.md5(goal.strip().lower().encode("utf-8")).hexdigest()[:12]


def _profile_path(goal: str) -> str:
    """Trả về đường dẫn file profile tương ứng với goal."""
    os.makedirs(PROFILES_DIR, exist_ok=True)
    return os.path.join(PROFILES_DIR, f"{_goal_hash(goal)}.json")


def load_profile(goal: str) -> dict | None:
    """
    Đọc profile từ file nếu đã tồn tại.
    Trả về dict hoặc None nếu chưa có.
    """
    path = _profile_path(goal)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_profile(profile: dict, goal: str) -> str:
    """Lưu profile ra file JSON. Trả về đường dẫn file."""
    path = _profile_path(goal)
    os.makedirs(PROFILES_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    return path


def compile_goal(goal: str) -> dict:
    """
    Gọi AI MỘT LẦN DUY NHẤT để tạo toàn bộ goal profile.
    Tự động fallback: Gemini → Groq → OpenAI.
    """
    from ai.llm_client import generate, extract_json

    prompt = f"""You are a market research assistant helping find relevant business livestreams and events.

User goal (in any language):
\"\"\"{goal}\"\"\"

Your task: Analyze this goal and return a comprehensive structured profile as ONLY valid JSON.

Return this exact structure:
{{
  "industries": ["list of 3-6 relevant business industries or fields"],
  "personas": ["list of 3-5 job titles or roles of target audience"],
  "topics": ["list of 8-15 specific searchable topics and keywords. Include SYNONYMS, related terms, and alternative phrasings. This is critical for finding events that use different terminology."],
  "search_queries": ["list of 15-25 ready-to-use search queries combining topics with event terms like 'live', 'webinar', 'workshop', 'summit', 'online event'"],
  "positive_keywords": ["list of 10-20 keywords that INCREASE relevance score if found in event title/description"],
  "negative_keywords": ["list of 10-15 keywords that DECREASE relevance score (off-topic content like gaming, anime, music, sports etc.)"]
}}

Rules:
- All queries and keywords must be in English (even if goal is in Vietnamese or other language)
- Topics must include synonyms and related technical terms
- Search queries should be diverse: some short (1-2 words), some long-tail (3-5 words)
- Negative keywords should be generic off-topic terms, not topic-specific

Example for goal "bán mỹ phẩm" (selling cosmetics):
{{
  "industries": ["beauty", "cosmetics", "skincare", "personal care", "ecommerce"],
  "personas": ["beauty brand owner", "cosmetics retailer", "ecommerce seller", "beauty distributor", "skincare founder"],
  "topics": ["beauty", "cosmetics", "skincare", "makeup", "personal care", "beauty ecommerce", "beauty brand", "skincare routine", "beauty startup", "cosmetics business", "beauty influencer", "beauty retail"],
  "search_queries": ["beauty ecommerce live", "skincare webinar", "cosmetics founder livestream", "beauty brand summit", "skincare business workshop", "cosmetics retail webinar", "beauty startup event", "makeup tutorial live", "skincare online event", "beauty industry networking"],
  "positive_keywords": ["beauty", "cosmetics", "skincare", "makeup", "personal care", "brand", "ecommerce", "retail", "founder", "business", "webinar", "summit", "networking"],
  "negative_keywords": ["gaming", "anime", "music", "sports", "minecraft", "roblox", "pubg", "football", "movie", "song", "karaoke", "fitness", "cooking"]
}}
"""

    response = generate(prompt, category="goal_compile")  # Tự động fallback Gemini → Groq → OpenAI
    text = extract_json(response.text)
    result = json.loads(text)

    profile = {
        "goal": goal,
        "compiled_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "compiled_by": f"{response.provider}/{response.model}",  # Lưu provider đã dùng
        "industries": result.get("industries", []),
        "personas": result.get("personas", []),
        "topics": result.get("topics", []),
        "search_queries": result.get("search_queries", []),
        "positive_keywords": result.get("positive_keywords", []),
        "negative_keywords": result.get("negative_keywords", []),
    }
    return profile


def get_or_compile(goal: str, force_recompile: bool = False) -> dict:
    """
    Logic chính:
    - Nếu đã có profile cho goal này và không yêu cầu compile lại -> load từ file
    - Nếu chưa có hoặc force_recompile=True -> gọi AI compile và lưu lại
    
    Returns: profile dict
    """
    if not force_recompile:
        existing = load_profile(goal)
        if existing:
            print(f"[Goal Profile] Dùng profile đã có (compiled: {existing.get('compiled_at', 'unknown')})")
            return existing

    print(f"[Goal Profile] Đang compile profile mới cho goal: '{goal}'...")
    try:
        profile = compile_goal(goal)
        path = save_profile(profile, goal)
        print(f"[Goal Profile] Đã lưu profile -> {path}")
        return profile
    except Exception as e:
        print(f"[Goal Profile] Lỗi compile, dùng fallback: {e}")
        return _fallback_profile(goal)


def _fallback_profile(goal: str) -> dict:
    """Tạo profile cơ bản không cần AI khi có lỗi."""
    import re
    words = re.findall(r'[a-zA-Z0-9]+', goal.lower())
    stop_words = {
        "livestream", "livestreams", "tim", "kiem", "khach", "hang",
        "and", "with", "the", "a", "an", "or", "in", "on", "at", "to",
        "by", "of", "for", "is", "are", "ban", "cho"
    }
    core = [w for w in words if w not in stop_words and len(w) > 2]

    suffixes = ["live", "livestream", "webinar", "workshop", "online event", "summit"]
    queries = [goal] + [f"{w} {s}" for w in core for s in suffixes]

    return {
        "goal": goal,
        "compiled_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "industries": core,
        "personas": [],
        "topics": core,
        "search_queries": queries[:20],
        "positive_keywords": core + ["webinar", "conference", "summit", "networking", "founder", "business"],
        "negative_keywords": ["gaming", "anime", "music", "sports", "minecraft", "roblox", "pubg", "football"],
    }


def list_profiles() -> list[dict]:
    """Trả về danh sách tất cả profile đã lưu."""
    os.makedirs(PROFILES_DIR, exist_ok=True)
    profiles = []
    for fname in os.listdir(PROFILES_DIR):
        if fname.endswith(".json"):
            fpath = os.path.join(PROFILES_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    profiles.append({
                        "goal": data.get("goal", ""),
                        "compiled_at": data.get("compiled_at", ""),
                        "query_count": len(data.get("search_queries", [])),
                        "file": fname,
                    })
            except Exception:
                pass
    return sorted(profiles, key=lambda x: x.get("compiled_at", ""), reverse=True)


def delete_profile(goal: str) -> bool:
    """Xóa profile của một goal."""
    path = _profile_path(goal)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False
