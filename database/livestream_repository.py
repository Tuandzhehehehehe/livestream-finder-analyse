from sqlalchemy import insert, select, update, delete
from sqlalchemy.exc import IntegrityError
import os
from openpyxl import load_workbook, Workbook

from database.db import engine, livestreams

EXCEL_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "livestreams.xlsx")
EXCEL_PATH = os.path.normpath(EXCEL_PATH)


def save_to_excel(event: dict) -> bool:
    """
    Lưu thông tin livestream vào file Excel kèm theo chỉ số đánh giá tiềm năng.
    Cột định dạng: Tên, Score, Priority, Buyer Persona, Industry, Suggested Comment, Location, Content, Ngày, YouTube, Meetup, X, TikTok, Eventbrite, LinkedIn
    """
    try:
        os.makedirs(os.path.dirname(EXCEL_PATH), exist_ok=True)

        headers = ['Tên', 'Score', 'Priority', 'Buyer Persona', 'Industry', 'Suggested Comment', 'Location', 'Content', 'Ngày', 'YouTube', 'Meetup', 'X', 'TikTok', 'Eventbrite', 'LinkedIn']

        if os.path.exists(EXCEL_PATH):
            wb = load_workbook(EXCEL_PATH)
            ws = wb.active
            # Cập nhật header nếu file Excel hiện tại chưa có các cột mới
            if ws.max_column < len(headers):
                ws.delete_rows(1, ws.max_row)
                ws.append(headers)
        else:
            wb = Workbook()
            ws = wb.active
            ws.title = "Livestreams"
            ws.append(headers)

        url = event.get("url", "").strip()
        if not url:
            return False

        url_exists = False
        for row in range(2, ws.max_row + 1):
            for col in range(10, 16):
                cell_val = ws.cell(row=row, column=col).value
                if cell_val and str(cell_val).strip() == url:
                    url_exists = True
                    break
            if url_exists:
                break

        if url_exists:
            return False

        title = event.get("title", "")
        score = event.get("score", 0)
        priority = event.get("priority", "Low")
        buyer_persona = event.get("buyer_persona", "")
        industry = event.get("industry", "")
        suggested_comment = event.get("suggested_comment", "")
        location = event.get("platform", "")
        content = event.get("description", "")
        date = event.get("scheduled_start_time") or event.get("start_time") or ""

        row_data = [title, score, priority, buyer_persona, industry, suggested_comment, location, content, date, "", "", "", "", "", ""]

        platform = str(event.get("platform", "")).lower().strip()
        if "youtube" in platform:
            row_data[9] = url
        elif "meetup" in platform:
            row_data[10] = url
        elif "x" in platform or "twitter" in platform:
            row_data[11] = url
        elif "tiktok" in platform:
            row_data[12] = url
        elif "eventbrite" in platform:
            row_data[13] = url
        elif "linkedin" in platform:
            row_data[14] = url

        ws.append(row_data)
        wb.save(EXCEL_PATH)
        return True
    except Exception as e:
        print(f"❌ Lỗi khi lưu vào Excel: {e}")
        return False




def save_event(event: dict) -> bool:
    """
    Lưu 1 livestream vào database.

    Returns:
        True  -> lưu thành công
        False -> livestream đã tồn tại hoặc lỗi
    """

    try:

        with engine.begin() as conn:

            stmt = insert(
                livestreams
            ).values(

                title=event["title"],

                platform=event.get(
                    "platform"
                ),

                description=event.get(
                    "description"
                ),

                url=event["url"],

                keyword=event.get(
                    "keyword"
                ),

                status=event.get(
                    "status"
                ),

                start_time=event.get(
                    "start_time"
                ),

                scheduled_start_time=event.get(
                    "scheduled_start_time"
                ),

                actual_start_time=event.get(
                    "actual_start_time"
                ),

                actual_end_time=event.get(
                    "actual_end_time"
                ),

                score=event.get(
                    "score"
                ),

                industry=event.get(
                    "industry"
                ),

                language=event.get(
                    "language"
                ),

                buyer_persona=event.get(
                    "buyer_persona"
                ),

                priority=event.get(
                    "priority"
                ),

                interaction_tip=event.get(
                    "interaction_tip"
                ),

                suggested_comment=event.get(
                    "suggested_comment"
                ),
            )

            conn.execute(stmt)

        save_to_excel(event)
        return True

    except IntegrityError:

        print(
            f"⚠️ Livestream đã tồn tại: {event.get('url')}"
        )
        save_to_excel(event)
        return False

    except Exception as e:

        print(
            f"❌ Lỗi khi lưu livestream: {e}"
        )
        return False


def get_all_events():
    """
    Lấy tất cả livestream
    """

    with engine.connect() as conn:

        result = conn.execute(
            select(livestreams)
        )

        return result.fetchall()


def get_event_by_id(
    event_id: int
):
    """
    Lấy livestream theo ID
    """

    with engine.connect() as conn:

        stmt = (
            select(livestreams)
            .where(
                livestreams.c.id
                == event_id
            )
        )

        return (
            conn.execute(stmt)
            .fetchone()
        )


def get_event_by_url(
    url: str
):
    """
    Tìm livestream theo URL
    """

    with engine.connect() as conn:

        stmt = (
            select(livestreams)
            .where(
                livestreams.c.url
                == url
            )
        )

        return (
            conn.execute(stmt)
            .fetchone()
        )


def update_classification_by_url(
    url: str,
    industry: str,
    language: str,
    buyer_persona: str,
    score: int
):
    """
    Cập nhật kết quả phân loại AI
    """

    with engine.begin() as conn:

        stmt = (
            update(
                livestreams
            )
            .where(
                livestreams.c.url
                == url
            )
            .values(
                industry=industry,
                language=language,
                buyer_persona=buyer_persona,
                score=score or 0,
            )
        )

        conn.execute(stmt)


def update_suggested_comment_by_url(
    url: str,
    suggested_comment: str
):
    """
    Cập nhật suggested_comment cho livestream
    """

    with engine.begin() as conn:

        stmt = (
            update(
                livestreams
            )
            .where(
                livestreams.c.url
                == url
            )
            .values(
                suggested_comment=suggested_comment
            )
        )

        conn.execute(stmt)


def delete_event_by_url(
    url: str
) -> bool:
    """
    Xóa livestream
    """

    with engine.begin() as conn:

        stmt = (
            delete(
                livestreams
            )
            .where(
                livestreams.c.url
                == url
            )
        )

        result = conn.execute(
            stmt
        )

        return (
            result.rowcount > 0
        )