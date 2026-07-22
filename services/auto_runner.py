"""
Auto Runner Service
===================
Pipeline tự động: đọc Goal Profiles → crawl → classify → lưu DB
Không cần mở Streamlit.

Dùng thư viện `schedule` để lập lịch.
"""

import sys
import json
import os
import time
import logging
from datetime import datetime, timezone
from typing import List, Optional

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ── Logger ──────────────────────────────────────────────────────────────────
LOG_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "auto_run.log"))
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

logger = logging.getLogger("auto_runner")
logger.setLevel(logging.INFO)

# File handler
_fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
_fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

# Console handler
_ch = logging.StreamHandler()
_ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

if not logger.handlers:
    logger.addHandler(_fh)
    logger.addHandler(_ch)


# ── Imports từ project ───────────────────────────────────────────────────────
def _import_project():
    """Import lazy để tránh circular import và load chậm khi import module."""
    from services.goal_profile_compiler import list_profiles
    from services.ai_crawl_tool import crawl_livestreams_with_ai
    from ai.classify import classify_event
    from ai.comments import generate_comments
    from database.livestream_repository import save_event
    return list_profiles, crawl_livestreams_with_ai, classify_event, generate_comments, save_event


# ── Core: chạy 1 lần ────────────────────────────────────────────────────────
def run_once(
    platforms: Optional[List[str]] = None,
    limit: int = 20,
    min_score: int = 10,
    auto_classify: bool = True,
    auto_comment: bool = True,
) -> dict:
    """
    Đọc tất cả Goal Profiles đã lưu, crawl từng goal, classify và lưu DB.

    Returns:
        dict: tóm tắt kết quả {total_new, total_skipped, profiles_run, errors}
    """
    list_profiles, crawl_livestreams_with_ai, classify_event, generate_comments, save_event = _import_project()

    profiles = list_profiles()
    if not profiles:
        logger.warning("Không có Goal Profile nào. Hãy compile ít nhất 1 profile trên Streamlit trước.")
        return {"total_new": 0, "total_skipped": 0, "profiles_run": 0, "errors": []}

    summary = {
        "total_new": 0,
        "total_skipped": 0,
        "profiles_run": 0,
        "errors": [],
        "run_at": datetime.now(timezone.utc).isoformat(),
    }

    for profile_info in profiles:
        goal = profile_info.get("goal", "")
        if not goal:
            continue

        logger.info(f"▶ Crawling goal: '{goal}'")

        try:
            result = crawl_livestreams_with_ai(
                goal,
                limit=limit,
                platforms=platforms,
                mode="ai_then_fallback",
                per_platform_timeout=20,
                cache=False,          # Auto-run luôn lấy data mới, không dùng cache
                force_recompile=False,
            )

            events = result.get("events", [])
            logger.info(f"  → Tìm được {len(events)} event (sau filter/score)")

            new_count = 0
            skipped_count = 0

            for event in events:
                url = event.get("url", "")
                if not url:
                    continue

                # ── Tự động Classify ──────────────────────────────────────
                if auto_classify:
                    try:
                        classification = classify_event(
                            event.get("title", ""),
                            event.get("description", ""),
                            goal=goal,
                        )
                        event.update({
                            "industry":        classification.get("industry", ""),
                            "buyer_persona":   classification.get("buyer_persona", ""),
                            "score":           classification.get("score", event.get("score", 0)),
                            "priority":        classification.get("priority", event.get("priority", "Low")),
                            "interaction_tip": classification.get("interaction_tip", ""),
                            "reason":          classification.get("reason", ""),
                            "suggested_comment": classification.get("suggested_comment", ""),
                        })
                    except Exception as e:
                        logger.warning(f"  Classify error for '{event.get('title', '')}': {e}")

                # ── Tự động Generate Comments ─────────────────────────────
                if auto_comment:
                    try:
                        suggestions = generate_comments(
                            event.get("title", ""),
                            event.get("description", ""),
                            goal=goal,
                        )
                        if suggestions:
                            event["suggested_comments"] = suggestions
                            if not event.get("suggested_comment"):
                                event["suggested_comment"] = suggestions[0]
                    except Exception as e:
                        logger.warning(f"  Comment error for '{event.get('title', '')}': {e}")

                # ── Lưu DB ────────────────────────────────────────────────
                try:
                    saved = save_event(event)
                    if saved:
                        new_count += 1
                        score_str = f"Score: {event.get('score', 0)} | Priority: {event.get('priority', 'Low')}"
                        logger.info(f"  ✔ Lưu: [{event.get('platform','?')}] [{score_str}] {event.get('title','')[:50]}")
                    else:
                        skipped_count += 1
                except Exception as e:
                    logger.error(f"  Save error: {e}")


            summary["total_new"] += new_count
            summary["total_skipped"] += skipped_count
            summary["profiles_run"] += 1

            # Ghi JSONL log
            _write_log_entry({
                "goal": goal,
                "new_events": new_count,
                "skipped": skipped_count,
                "total_found": len(events),
                "status": "ok",
            })

            logger.info(f"  ✅ Goal '{goal}': {new_count} mới, {skipped_count} bỏ qua\n")

        except Exception as e:
            err_msg = f"Goal '{goal}': {e}"
            logger.error(f"  ❌ Lỗi: {err_msg}")
            summary["errors"].append(err_msg)
            _write_log_entry({"goal": goal, "status": "error", "error": str(e)})

    logger.info(
        f"🏁 Hoàn tất: {summary['total_new']} event mới, "
        f"{summary['total_skipped']} bỏ qua, "
        f"{len(summary['errors'])} lỗi"
    )
    return summary


# ── JSONL log helper ─────────────────────────────────────────────────────────
def _write_log_entry(data: dict):
    data["timestamp"] = datetime.now(timezone.utc).isoformat()
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
    except Exception:
        pass


def read_log_entries(n: int = 50) -> List[dict]:
    """Đọc n dòng log cuối cùng để hiển thị trên Dashboard."""
    if not os.path.exists(LOG_PATH):
        return []
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        entries = []
        for line in reversed(lines[-n:]):
            try:
                entries.append(json.loads(line.strip()))
            except Exception:
                pass
        return entries
    except Exception:
        return []


# ── Scheduler ────────────────────────────────────────────────────────────────
def start_scheduler(
    interval_hours: float = 2.0,
    platforms: Optional[List[str]] = None,
    limit: int = 20,
    auto_classify: bool = True,
    auto_comment: bool = True,
):
    """
    Chạy run_once() mỗi interval_hours giờ.
    Block mãi cho đến khi bị dừng (Ctrl+C).
    """
    import schedule

    logger.info(f"🕐 Scheduler khởi động — mỗi {interval_hours} giờ sẽ crawl tự động")
    logger.info(f"   Platforms: {platforms or 'tất cả'} | Limit: {limit} | Classify: {auto_classify} | Comment: {auto_comment}")

    def _job():
        logger.info("=" * 60)
        logger.info(f"⏰ Auto-run triggered lúc {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)
        run_once(
            platforms=platforms,
            limit=limit,
            auto_classify=auto_classify,
            auto_comment=auto_comment,
        )

    # Chạy 1 lần ngay khi khởi động
    _job()

    # Sau đó lập lịch
    schedule.every(interval_hours).hours.do(_job)

    try:
        while True:
            schedule.run_pending()
            time.sleep(30)  # Check lịch mỗi 30 giây
    except KeyboardInterrupt:
        logger.info("⛔ Scheduler dừng lại (Ctrl+C)")
