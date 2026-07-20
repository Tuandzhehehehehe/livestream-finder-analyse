import os
import sys
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()

from database.db import engine, livestreams
from sqlalchemy import select, update
from ai.classify import classify_event
from ai.comments import generate_comments
from database.livestream_repository import save_to_excel
from openpyxl import Workbook

EXCEL_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "data", "livestreams.xlsx"))

headers = ['Tên', 'Score', 'Priority', 'Buyer Persona', 'Industry', 'Suggested Comment', 'Location', 'Content', 'Ngày', 'YouTube', 'Meetup', 'X', 'TikTok', 'Eventbrite', 'LinkedIn']

# Create clean Excel file
os.makedirs(os.path.dirname(EXCEL_PATH), exist_ok=True)
wb = Workbook()
ws = wb.active
ws.title = "Livestreams"
ws.append(headers)
wb.save(EXCEL_PATH)

with engine.connect() as conn:
    rows = conn.execute(select(livestreams)).mappings().fetchall()

print("=" * 60)
print(f"📊 Đang chạy đánh giá lại cho {len(rows)} sự kiện trong CSDL...")
print("=" * 60)

updated_count = 0
from services.ai_crawl_tool import infer_event_status

from services.relevance_filter import calculate_relevance

for row in rows:
    event = dict(row)
    goal = event.get("keyword") or "Tokenization livestream"
    
    status = infer_event_status(event)
    event["status"] = status
    
    # Run MiniLM & Rule-based relevance scoring
    rel_score = calculate_relevance(event, {}, goal=goal)

    # Run classification if rel_score >= 50
    if rel_score >= 50:
        classification = classify_event(
            event.get("title", ""),
            event.get("description", ""),
            goal=goal
        )
        comments = generate_comments(
            event.get("title", ""),
            event.get("description", ""),
            goal=goal
        )
        suggested_comment = comments[0] if comments else classification.get("suggested_comment", "")
        score = classification.get("score", rel_score)
        priority = classification.get("priority", "High")
        buyer_persona = classification.get("buyer_persona", "Target Audience")
        industry = classification.get("industry", "Technology")
        interaction_tip = classification.get("interaction_tip", "Join with a relevant question.")
    else:
        suggested_comment = ""
        score = rel_score
        priority = "Low"
        buyer_persona = "Unknown"
        industry = "General"
        interaction_tip = "Join with a relevant question."

    
    # Update SQLite database
    with engine.begin() as conn:
        stmt = (
            update(livestreams)
            .where(livestreams.c.id == event["id"])
            .values(
                status=status,
                score=score,
                priority=priority,
                buyer_persona=buyer_persona,
                industry=industry,
                suggested_comment=suggested_comment,
                interaction_tip=interaction_tip
            )
        )
        conn.execute(stmt)
    
    # Update dictionary and export to Excel
    event.update({
        "score": score,
        "priority": priority,
        "buyer_persona": buyer_persona,
        "industry": industry,
        "suggested_comment": suggested_comment
    })
    
    save_to_excel(event)
    updated_count += 1
    print(f"  ✔ [{event.get('platform','?')}] [Score: {int(score):2d} | Priority: {priority:6s}] {event.get('title','')[:55]}")

print("=" * 60)
print(f"✅ Đã hoàn tất đánh giá lại {updated_count} sự kiện!")
print(f"📁 File Excel đã được cập nhật tại: {EXCEL_PATH}")
print("=" * 60)
