
import inspect
import os
import streamlit as st
import pandas as pd

from services.search_agent import search_livestreams
from services.ai_crawl_tool import crawl_livestreams_with_ai
from ai.classify import classify_event
from database.livestream_repository import save_event
from crawler.session_login import login_interactive_gui

try:
    from crawler.eventbrite import crawl_eventbrite
except Exception:
    crawl_eventbrite = None

st.set_page_config(
    page_title="AI Livestream Finder",
    layout="wide",
)

# =====================================
# SIDEBAR LOGIN MANAGEMENT
# =====================================
with st.sidebar:
    st.write("## 🔑 Quản lý Đăng nhập")
    st.info(
        "Nhấn nút dưới để mở trình duyệt đăng nhập X, TikTok hoặc LinkedIn. "
        "Hãy đăng nhập tài khoản của bạn, sau đó **đóng cửa sổ trình duyệt lại** để hoàn tất!"
    )
    
    if st.button("Đăng nhập X (Twitter)", use_container_width=True):
        with st.spinner("Đang mở trình duyệt đăng nhập X..."):
            success, msg = login_interactive_gui("x")
            if success:
                st.success(msg)
            else:
                st.error(msg)
                
    if st.button("Đăng nhập TikTok", use_container_width=True):
        with st.spinner("Đang mở trình duyệt đăng nhập TikTok..."):
            success, msg = login_interactive_gui("tiktok")
            if success:
                st.success(msg)
            else:
                st.error(msg)

    if st.button("Đăng nhập LinkedIn", use_container_width=True):
        with st.spinner("Đang mở trình duyệt đăng nhập LinkedIn..."):
            success, msg = login_interactive_gui("linkedin")
            if success:
                st.success(msg)
            else:
                st.error(msg)

    st.write("---")
    st.write("## 📊 Xuất dữ liệu")
    excel_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "livestreams.xlsx"))
    if os.path.exists(excel_path):
        try:
            with open(excel_path, "rb") as f:
                excel_data = f.read()
            st.download_button(
                label="📥 Tải xuống file Excel",
                data=excel_data,
                file_name="livestreams.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="sidebar_download_excel"
            )
        except Exception as e:
            st.error(f"Lỗi khi đọc file Excel: {e}")
    else:
        st.info("Chưa có dữ liệu Excel. Hãy thực hiện tìm kiếm.")

st.title(
    "🎯 AI Multi-Platform Livestream Finder"
)

st.caption(
    "Tìm livestream, webinar, workshop, networking event bằng AI"
)

# =====================================
# SEARCH FORM
# =====================================

with st.form("search_form"):

    col1, col2 = st.columns(
        [2, 1]
    )

    with col1:

        goal = st.text_area(
            "Bạn muốn tìm khách hàng ở lĩnh vực nào?",
            placeholder="""
Ví dụ:

AI Automation cho doanh nghiệp

Fintech Startup

SaaS Founder

Digital Marketing Agency

Ecommerce Seller
""",
            height=180,
        )

    with col2:

        status_filter = st.selectbox(
            "Trạng thái",
            [
                "ALL",
                "LIVE",
                "UPCOMING",
                "COMPLETED"
            ],
        )

        enable_ai = st.checkbox(
            "Đánh giá bằng AI",
            value=False,
        )

        use_ai_crawl = st.checkbox(
            "Sử dụng AI Crawl Tool",
            value=True,
        )

        ai_mode = st.selectbox(
            "Chế độ AI / Fallback",
            [
                "AI then Fallback",
                "Fallback only",
            ],
            index=0,
        )

        platform_options = [
            "youtube",
            "meetup",
            "x",
            "tiktok",
            "linkedin",
            "web",
        ]

        if crawl_eventbrite:
            platform_options.append("eventbrite")

        selected_platforms = st.multiselect(
            "Nền tảng",
            platform_options,
            default=["linkedin"] if "linkedin" in platform_options else platform_options,
        )

        enable_cache = st.checkbox(
            "Enable per-platform cache",
            value=True,
        )

        cache_ttl = st.number_input(
            "Cache TTL (seconds)",
            min_value=0,
            max_value=86400,
            value=300,
        )

        use_headless = st.checkbox(
            "Use headless browser for X/TikTok/LinkedIn",
            value=False,
        )

        prefer_fast = st.checkbox(
            "Prefer fast platforms (meetup,youtube first)",
            value=True,
        )

        limit = st.number_input(
            "Số lượng",
            min_value=1,
            max_value=100,
            value=20,
        )

        st.write("")
        st.write("")

        search_btn = st.form_submit_button(
            "🔍 Tìm kiếm",
            use_container_width=True,
        )

# =====================================
# SEARCH
# =====================================

# Cache purge button must be outside the form per Streamlit rules
if st.button("Xoá cache nền tảng"):
    cache_db = os.path.join(os.path.dirname(__file__), "..", "data", "platform_cache.sqlite")
    cache_db = os.path.normpath(cache_db)
    try:
        if os.path.exists(cache_db):
            os.remove(cache_db)
            st.success("Đã xóa cache nền tảng.")
        else:
            st.info("Không tìm thấy file cache.")
    except Exception as e:
        st.error(f"Lỗi khi xóa cache: {e}")


if search_btn:

    if not goal.strip():

        st.warning(
            "Vui lòng nhập mục tiêu tìm kiếm."
        )

        st.stop()

    with st.spinner(
        "🤖 AI đang phân tích mục tiêu..."
    ):

        if use_ai_crawl:

            mode = "ai_then_fallback" if ai_mode == "AI then Fallback" else "fallback_only"

            # reorder selected platforms if prefer_fast
            if prefer_fast and selected_platforms:
                preferred = [p for p in ["meetup", "youtube"] if p in selected_platforms]
                rest = [p for p in selected_platforms if p not in preferred]
                selected_platforms = preferred + rest

            # call defensively in case runtime function signature differs
            sig = inspect.signature(crawl_livestreams_with_ai)
            kwargs = {
                "per_platform_timeout": 20,
                "cache": bool(enable_cache),
                "cache_ttl": int(cache_ttl),
                "use_headless": bool(use_headless),
            }

            if "mode" in sig.parameters:
                agent_result = crawl_livestreams_with_ai(
                    goal,
                    limit,
                    platforms=selected_platforms,
                    mode=mode,
                    **kwargs,
                )
            else:
                # older signature: (goal, limit, platforms=None)
                agent_result = crawl_livestreams_with_ai(
                    goal,
                    limit,
                    selected_platforms,
                )

        else:

            agent_result = (
                search_livestreams(
                    goal,
                    limit,
                    use_headless=bool(use_headless),
                )
            )

    queries = agent_result.get(
        "queries",
        []
    )

    events = agent_result.get(
        "events",
        []
    )

    st.write(
        "### Search Queries"
    )

    st.write(
        queries
    )

    if use_ai_crawl:
        st.write(
            f"**Mode:** {ai_mode}"
        )
        st.write(
            f"**Fallback mode active:** {'Yes' if mode == 'fallback_only' else 'No'}"
        )
        st.write(
            f"**Fallback branch executed:** {'Yes' if agent_result.get('used_fallback', False) else 'No'}"
        )

    if status_filter != "ALL":

        events = [

            event

            for event in events

            if event.get(
                "status"
            ) == status_filter
        ]

    st.success(
        f"Tìm thấy {len(events)} sự kiện"
    )

    results = []

    progress = st.progress(0)

    status_placeholder = st.empty()

    total = len(events)

    if total == 0:

        st.warning(
            "Không tìm thấy livestream phù hợp."
        )

    else:

        if status_filter == "COMPLETED":
            events = [e for e in events if e.get("status") == "COMPLETED" and e.get("actual_start_time") and e.get("actual_end_time")]
        else:
            events = [e for e in events if status_filter == "ALL" or e.get("status") == status_filter]
        
        total = len(events)
        
        if total == 0:
            st.warning("Không tìm thấy livestream phù hợp với bộ lọc hiện tại.")
        else:
            for index, event in enumerate(events):

                current = index + 1

                status_placeholder.info(
                    f"⏳ Đang xử lý {current}/{total}"
                )

                if enable_ai:
                    match_score = event.get("_match_score", 0)
                    if match_score >= 15:
                        try:
                            ai_result = (
                                classify_event(
                                    event.get("title", ""),
                                    event.get("description", ""),
                                    goal
                                )
                            )
                            event.update(ai_result)
                            
                            # Tích hợp tính năng tạo comment tự động
                            from ai.comments import generate_comments
                            comments = generate_comments(
                                event.get("title", ""),
                                event.get("description", ""),
                                goal
                            )
                            if comments:
                                event["suggested_comment"] = " | ".join(comments)
                                
                        except Exception as e:
                            st.warning(f"AI Error: {e}")
                    else:
                        event["priority"] = "Low"
                        event["interaction_tip"] = "Điểm liên quan thấp, bỏ qua đánh giá AI để tiết kiệm quota."

                    # Đảm bảo điểm hiển thị (score) không thấp hơn điểm nội bộ (_match_score)
                    current_score = event.get("score", 0)
                    match_score = event.get("_match_score", 0)
                    if match_score > current_score:
                        event["score"] = match_score
                        
                    if event.get("score", 0) >= 80:
                        event["priority"] = "High"
                    elif event.get("score", 0) >= 50:
                        event["priority"] = "Medium"

                try:
                    save_event(event)
                except Exception:
                    pass

                results.append(event)

                progress.progress(current / total)

        status_placeholder.success(
            f"✅ Hoàn thành {total} sự kiện"
        )

    # =====================================
    # GOOGLE DORKING (OSINT)
    # =====================================
    st.write("---")
    st.write("## 🌍 Tự động mở rộng tìm kiếm trên Google (OSINT)")
    st.info("Vì lý do bảo mật, các bot tự động thường bị Google chặn. Tuy nhiên, bạn có thể tự mình bấm vào các liên kết bên dưới")
    st.markdown("### Hoặc tự tìm thủ công trên Google (Google Dorking)")
    st.write("Dưới đây là các đường link tìm kiếm chuyên sâu để bạn tự click vào nếu muốn tìm tay:")

    import urllib.parse
    dork_query1 = urllib.parse.quote_plus(f'site:linkedin.com/events/ "{goal}"')
    dork_query2 = urllib.parse.quote_plus(f'site:linkedin.com/posts/ "{goal}" (livestream OR webinar OR "virtual event") ("register" OR "join")')
    dork_query3 = urllib.parse.quote_plus(f'"{goal}" (livestream OR webinar OR "virtual event") ("register" OR "tickets" OR "join" OR "save your spot") -news -blog')

    st.markdown(f"- [Tìm Sự kiện chính thức trên LinkedIn (Events)](https://www.google.com/search?q={dork_query1})")
    st.markdown(f"- [Tìm bài đăng kêu gọi Livestream/Webinar trên LinkedIn](https://www.google.com/search?q={dork_query2})")
    st.markdown(f"- [Tìm Livestream/Webinar trên toàn bộ Internet (Bất kỳ Website nào)](https://www.google.com/search?q={dork_query3})")
    st.write("---")

    # =====================================
    # TABLE
    # =====================================

    if results:

        st.write(
            "## KẾT QUẢ"
        )

        df = pd.DataFrame(
            results
        )

        df = df.rename(
            columns={
                "title": "Tiêu đề",
                "platform": "Nền tảng",
                "status": "Trạng thái",
                "industry": "Ngành nghề",
                "language": "Ngôn ngữ",
                "buyer_persona": "Khách hàng mục tiêu",
                "score": "Điểm",
                "priority": "Ưu tiên",
                "interaction_tip": "Gợi ý tương tác",
                "url": "Link",
                "scheduled_start_time": "Scheduled Start",
                "actual_start_time": "Actual Start",
                "actual_end_time": "Actual End",
            }
        )

        show_columns = [

            col

            for col in [

                "Tiêu đề",

                "Nền tảng",

                "Trạng thái",

                "Ngành nghề",

                "Khách hàng mục tiêu",

                "Điểm",

                "Priority",

                "Scheduled Start",
                
                "Actual Start",
                
                "Actual End",

                "Link",

            ]

            if col in df.columns
        ]

        st.dataframe(
            df[
                show_columns
            ],
            use_container_width=True,
        )

        excel_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "livestreams.xlsx"))
        if os.path.exists(excel_path):
            try:
                with open(excel_path, "rb") as f:
                    excel_data = f.read()
                st.download_button(
                    label="📥 Tải xuống toàn bộ file Excel kết quả",
                    data=excel_data,
                    file_name="livestreams.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_excel_results"
                )
            except Exception as e:
                pass

        # =====================================
        # DETAILS
        # =====================================

        st.write(
            "## CHI TIẾT"
        )

        for event in results:

            platform_icon = {

                "YouTube": "📺",

                "Meetup": "🤝",

                "Eventbrite": "🎟️",

                "Twitch": "🎮",

                "LinkedIn": "💼",
            }

            icon = platform_icon.get(
                event.get(
                    "platform"
                ),
                "📌"
            )

            with st.expander(

                f"{icon} {event.get('title')}"

            ):

                st.write(
                    f"**Platform:** {event.get('platform')}"
                )

                st.write(
                    f"**Status:** {event.get('status')}"
                )

                st.write(
                    f"**Industry:** {event.get('industry')}"
                )

                st.write(
                    f"**Score:** {event.get('score')}"
                )

                st.write(
                    f"**Language:** {event.get('language')}"
                )

                st.write(
                    f"**Buyer Persona:** {event.get('buyer_persona')}"
                )

                st.write(
                    f"**Scheduled Start:** {event.get('scheduled_start_time')}"
                )

                st.write(
                    f"**Actual Start:** {event.get('actual_start_time')}"
                )

                st.write(
                    f"**Actual End:** {event.get('actual_end_time')}"
                )

                st.write(
                    f"**Reason:** {event.get('reason')}"
                )

                st.write(
                    f"**URL:** {event.get('url')}"
                )

                st.write(
                    f"**Suggested Comment:** {event.get('suggested_comment')}"
                )