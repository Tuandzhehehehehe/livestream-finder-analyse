"""
database/livestream_repository.py — Database & Excel Persistence Layer
========================================================================
"""

import os
from openpyxl import load_workbook, Workbook
# pyrefly: ignore [missing-import]
from sqlalchemy import select, update, delete
# pyrefly: ignore [missing-import]
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from database.db import engine, livestreams

EXCEL_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "livestreams.xlsx"))
EXCEL_HEADERS = ['Tên', 'Location', 'Content', 'Ngày', 'YouTube', 'Meetup', 'X', 'TikTok', 'Eventbrite', 'LinkedIn']
PLATFORM_COL_INDEX = {"youtube": 4, "meetup": 5, "x": 6, "twitter": 6, "tiktok": 7, "eventbrite": 8, "linkedin": 9}


def save_to_excel(event: dict) -> bool:
    try:
        os.makedirs(os.path.dirname(EXCEL_PATH), exist_ok=True)
        if os.path.exists(EXCEL_PATH):
            wb = load_workbook(EXCEL_PATH)
            ws = wb.active
            if ws.max_column < len(EXCEL_HEADERS):
                for idx, h in enumerate(EXCEL_HEADERS, 1):
                    ws.cell(row=1, column=idx, value=h)
        else:
            wb = Workbook()
            ws = wb.active
            ws.title = "Livestreams"
            ws.append(EXCEL_HEADERS)

        url = event.get("url", "").strip()
        if not url:
            return False

        for row in range(2, ws.max_row + 1):
            for col in range(5, 11):
                if str(ws.cell(row=row, column=col).value or "").strip() == url:
                    return False

        row_data = [
            event.get("title", ""), event.get("platform", ""), event.get("description", ""),
            event.get("scheduled_start_time") or event.get("start_time") or "", "", "", "", "", "", ""
        ]
        plat = str(event.get("platform", "")).lower().strip()
        for p_key, col_idx in PLATFORM_COL_INDEX.items():
            if p_key in plat:
                row_data[col_idx] = url
                break

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
        return conn.execute(select(livestreams)).fetchall()


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