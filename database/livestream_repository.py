"""
database/livestream_repository.py — Database & Excel Persistence Layer
========================================================================
"""

import os
from openpyxl import load_workbook, Workbook
# pyrefly: ignore [missing-import]
from sqlalchemy import select, update, delete, func as sqlfunc
# pyrefly: ignore [missing-import]
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from database.db import engine, livestreams

EXCEL_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "livestreams.xlsx"))
EXCEL_HEADERS = ["Tên", "Score", "Priority", "Buyer Persona", "Industry", "Suggested Comment", "Location", "Content", "Ngày", "YouTube", "TikTok", "Web"]


ALLOWED_PLATFORMS_LOWER = ["youtube", "tiktok", "web"]


def purge_legacy_platforms():
    """Xoá các event thuộc nền tảng cũ (LinkedIn, Meetup, X, Eventbrite, ...)."""
    try:
        with engine.begin() as conn:
            conn.execute(
                delete(livestreams).where(
                    sqlfunc.lower(livestreams.c.platform).notin_(ALLOWED_PLATFORMS_LOWER)
                )
            )
    except Exception as e:
        print(f"❌ Error purging legacy platforms: {e}")


# Auto-purge legacy platforms on module load
try:
    purge_legacy_platforms()
except Exception:
    pass


def save_to_excel(event: dict) -> bool:
    """
    Lưu thông tin livestream vào file Excel.
    Cột: Tên, Score, Priority, Buyer Persona, Industry, Suggested Comment, Location, Content, Ngày, YouTube, TikTok, Web
    """
    try:
        os.makedirs(os.path.dirname(EXCEL_PATH), exist_ok=True)

        if os.path.exists(EXCEL_PATH):
            try:
                wb = load_workbook(EXCEL_PATH)
                ws = wb.active
                # Cập nhật header nếu file hiện tại chưa có đủ cột
                if ws.max_column < len(EXCEL_HEADERS):
                    ws.delete_rows(1, ws.max_row)
                    ws.append(EXCEL_HEADERS)
            except Exception as e:
                print(f"[Excel Repair] File bị lỗi ({e}) — tạo lại file mới...")
                wb = Workbook()
                ws = wb.active
                ws.title = "Livestreams"
                ws.append(EXCEL_HEADERS)
        else:
            wb = Workbook()
            ws = wb.active
            ws.title = "Livestreams"
            ws.append(EXCEL_HEADERS)

        url = event.get("url", "").strip()
        if not url:
            return False

        # Kiểm tra URL đã tồn tại (cột 10–12)
        for row in range(2, ws.max_row + 1):
            for col in range(10, 13):
                if ws.cell(row=row, column=col).value and str(ws.cell(row=row, column=col).value).strip() == url:
                    return False

        row_data = [
            event.get("title", ""),
            event.get("score", 0),
            event.get("priority", "Low"),
            event.get("buyer_persona", ""),
            event.get("industry", ""),
            event.get("suggested_comment", ""),
            event.get("platform", ""),
            event.get("description", ""),
            event.get("scheduled_start_time") or event.get("start_time") or "",
            "", "", "",
        ]
        platform = str(event.get("platform", "")).lower().strip()
        if "youtube" in platform:
            row_data[9] = url
        elif "tiktok" in platform:
            row_data[10] = url
        else:
            row_data[11] = url

        ws.append(row_data)
        wb.save(EXCEL_PATH)
        return True
    except Exception as e:
        print(f"❌ Excel save error: {e}")
        return False


def save_event(event: dict) -> bool:
    try:
        with engine.begin() as conn:
            stmt = sqlite_insert(livestreams).values(
                title=event["title"],
                platform=event.get("platform"),
                description=event.get("description"),
                url=event["url"],
                keyword=event.get("keyword"),
                status=event.get("status"),
                start_time=event.get("start_time"),
                scheduled_start_time=event.get("scheduled_start_time"),
                actual_start_time=event.get("actual_start_time"),
                actual_end_time=event.get("actual_end_time"),
                score=event.get("score"),
                industry=event.get("industry"),
                language=event.get("language"),
                buyer_persona=event.get("buyer_persona"),
                priority=event.get("priority"),
                interaction_tip=event.get("interaction_tip"),
                suggested_comment=event.get("suggested_comment"),
            ).on_conflict_do_nothing(index_elements=["url"])

            res = conn.execute(stmt)
            if res.rowcount > 0:
                save_to_excel(event)
                return True
            return False
    except Exception as e:
        print(f"❌ Save event error: {e}")
        return False


def get_all_events():
    with engine.connect() as conn:
        return conn.execute(
            select(livestreams).where(
                sqlfunc.lower(livestreams.c.platform).in_(ALLOWED_PLATFORMS_LOWER)
            )
        ).fetchall()


def get_event_by_id(event_id: int):
    with engine.connect() as conn:
        return conn.execute(select(livestreams).where(livestreams.c.id == event_id)).fetchone()


def get_event_by_url(url: str):
    with engine.connect() as conn:
        return conn.execute(select(livestreams).where(livestreams.c.url == url)).fetchone()


def update_classification_by_url(url: str, industry: str, language: str, buyer_persona: str, score: int):
    with engine.begin() as conn:
        conn.execute(update(livestreams).where(livestreams.c.url == url).values(
            industry=industry, language=language, buyer_persona=buyer_persona, score=score or 0
        ))


def update_suggested_comment_by_url(url: str, suggested_comment: str):
    with engine.begin() as conn:
        conn.execute(update(livestreams).where(livestreams.c.url == url).values(suggested_comment=suggested_comment))


def delete_event_by_url(url: str) -> bool:
    with engine.begin() as conn:
        res = conn.execute(delete(livestreams).where(livestreams.c.url == url))
        return res.rowcount > 0


def get_summary_stats() -> dict:
    """Tổng hợp thống kê toàn bộ events trong DB (chỉ tính các platform hợp lệ: YouTube, TikTok, Web)."""
    base_where = sqlfunc.lower(livestreams.c.platform).in_(ALLOWED_PLATFORMS_LOWER)

    def _group(conn, col):
        rows = conn.execute(
            select(col, sqlfunc.count(livestreams.c.id))
            .where(base_where)
            .group_by(col)
        ).fetchall()
        return {(r[0] or "unknown"): r[1] for r in rows}

    with engine.connect() as conn:
        return {
            "total_events":      conn.execute(select(sqlfunc.count(livestreams.c.id)).where(base_where)).scalar() or 0,
            "by_platform":       _group(conn, livestreams.c.platform),
            "by_priority":       _group(conn, livestreams.c.priority),
            "by_status":         _group(conn, livestreams.c.status),
            "avg_score":         round(float(conn.execute(select(sqlfunc.avg(livestreams.c.score)).where(base_where)).scalar() or 0), 1),
            "top_score":         int(conn.execute(select(sqlfunc.max(livestreams.c.score)).where(base_where)).scalar() or 0),
            "latest_crawled_at": str(v)[:19] if (v := conn.execute(select(sqlfunc.max(livestreams.c.created_at)).where(base_where)).scalar()) else "–",
        }