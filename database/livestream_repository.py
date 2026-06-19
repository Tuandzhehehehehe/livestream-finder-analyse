from sqlalchemy import insert, select, update, delete
from sqlalchemy.exc import IntegrityError

from database.db import engine, livestreams


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

        return True

    except IntegrityError:

        print(
            f"⚠️ Livestream đã tồn tại: {event.get('url')}"
        )

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