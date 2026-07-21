
import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import inspect
import os
import streamlit as st
import pandas as pd


from services.search_agent import search_livestreams
from services.ai_crawl_tool import crawl_livestreams_with_ai
from ai.classify import classify_event
from database.livestream_repository import save_event
from crawler.session_login import login_interactive_gui
from services.goal_profile_compiler import get_or_compile, load_profile, list_profiles, delete_profile

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

    st.write("---")
    st.write("## 🧠 Goal Profiles")
    st.caption("Mỗi profile được compile 1 lần và tái sử dụng, tiết kiệm token AI")
    all_profiles = list_profiles()
    if all_profiles:
        import json as _json
        for p in all_profiles:
            col_p, col_del = st.columns([3, 1])
            with col_p:
                st.markdown(f"**{p['goal']}**  \n⏰ {p['compiled_at']} — {p['query_count']} queries")
            with col_del:
                if st.button("🗑️", key=f"del_{p['file']}", help="Xóa profile này"):
                    delete_profile(p['goal'])
                    st.rerun()
    else:
        st.info("Chưa có profile nào.")

    st.write("---")
    st.write("## ⚙️ Auto-Run")
    st.caption("Tự động crawl + classify + lưu DB theo lịch")

    auto_run_log_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "auto_run.log"))

    # ── Cấu hình interval ────────────────────────────────────────────
    ar_interval = st.number_input(
        "⏱ Khoảng cách giữa các lần crawl (giờ)",
        min_value=0.5,
        max_value=72.0,
        value=24.0,
        step=0.5,
        help="Khuyên dùng ≥ 24h để API key (Gemini + YouTube) kịp reset quota hàng ngày",
        key="ar_interval",
    )

    ar_platforms_all = ["📹 Video Platforms (YouTube, TikTok)", "youtube", "tiktok", "meetup", "linkedin", "x", "web"]
    if crawl_eventbrite:
        ar_platforms_all.append("eventbrite")

    ar_platforms = st.multiselect(
        "🌐 Platforms",
        ar_platforms_all,
        default=["📹 Video Platforms (YouTube, TikTok)"],
        key="ar_platforms",
    )

    ar_col1, ar_col2 = st.columns(2)
    with ar_col1:
        ar_classify = st.checkbox("🤖 Auto-Classify", value=True, key="ar_classify")
    with ar_col2:
        ar_comment = st.checkbox("💬 Auto-Comment", value=False, key="ar_comment",
                                  help="Tắt để tiết kiệm token AI")

    # ── Nút chạy thủ công 1 lần ──────────────────────────────────────
    if st.button("▶️ Chạy thủ công ngay", use_container_width=True, key="manual_auto_run"):
        with st.spinner("🤖 Đang crawl tất cả Goal Profiles..."):
            try:
                from services.auto_runner import run_once
                summary = run_once(
                    platforms=ar_platforms if ar_platforms else None,
                    auto_classify=ar_classify,
                    auto_comment=ar_comment,
                )
                st.success(
                    f"✅ Hoàn tất! "
                    f"**{summary['total_new']}** event mới | "
                    f"**{summary['total_skipped']}** bỏ qua | "
                    f"**{summary['profiles_run']}** profiles"
                )
                if summary["errors"]:
                    st.warning(f"⚠️ {len(summary['errors'])} lỗi: " + "; ".join(summary["errors"][:2]))
                st.rerun()
            except Exception as e:
                st.error(f"Lỗi: {e}")

    # ── Lệnh terminal động theo cấu hình ─────────────────────────────
    cmd_parts = [f"py auto_crawl.py --interval {ar_interval}"]
    if ar_platforms:
        cmd_parts.append(f"--platforms {' '.join(ar_platforms)}")
    if not ar_classify:
        cmd_parts.append("--no-classify")
    if not ar_comment:
        cmd_parts.append("--no-comment")

    st.caption("💡 Để chạy theo lịch tự động, mở terminal mới và chạy:")
    st.code(" ".join(cmd_parts), language="bash")
    st.caption(f"⚠️ Khuyến nghị: interval ≥ 24h để tránh cạn quota API (hiện tại: **{ar_interval}h**)")

    # ── Log gần nhất ─────────────────────────────────────────────────
    if os.path.exists(auto_run_log_path):
        try:
            from services.auto_runner import read_log_entries
            log_entries = read_log_entries(20)
            if log_entries:
                with st.expander("📋 Log Auto-Run gần nhất", expanded=False):
                    log_rows = []
                    for entry in log_entries:
                        ts = entry.get("timestamp", "")[:16].replace("T", " ")
                        goal = entry.get("goal", "")[:30]
                        status = "✅" if entry.get("status") == "ok" else "❌"
                        new_ev = entry.get("new_events", "-")
                        skipped = entry.get("skipped", "-")
                        log_rows.append({"Thời gian": ts, "Goal": goal, "Status": status, "Mới": new_ev, "Bỏ qua": skipped})
                    if log_rows:
                        st.dataframe(pd.DataFrame(log_rows), use_container_width=True, height=200)
        except Exception:
            pass

    st.write("---")
    st.write("## 🧠 AI Providers")
    try:
        from ai.llm_client import available_providers
        providers = available_providers()
        provider_labels = {
            "gemini": "🟢 Gemini (Google)",
            "groq": "🟢 Groq (Free — Llama/Mixtral)",
            "openai": "🟢 OpenAI (GPT)",
        }
        all_providers = ["gemini", "groq", "openai"]
        for p in all_providers:
            if p in providers:
                st.markdown(provider_labels.get(p, f"🟢 {p}"))
            else:
                st.markdown(f"🔴 {p.capitalize()} — *chưa có API key*")
        if len(providers) < 2:
            st.caption("💡 Thêm key vào `.env` để dùng nhiều provider, tránh hết quota:")
            st.code("GROQ_API_KEY=gsk_...\nOPENAI_API_KEY=sk-...", language="text")
    except Exception:
        st.info("Không thể kiểm tra AI providers.")

    st.write("---")
    st.write("## 🪙 Lịch sử dùng Token AI")


    token_log_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "token_usage.log"))
    if os.path.exists(token_log_path):
        try:
            import json, time
            records = []
            with open(token_log_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        d = json.loads(line)
                        d["time"] = time.strftime('%H:%M:%S', time.localtime(d.get("timestamp")))
                        records.append(d)
                    except:
                        pass
            if records:
                token_df = pd.DataFrame(records)
                if not token_df.empty:
                    token_df = token_df[["time", "model", "prompt_tokens", "candidate_tokens", "total_tokens"]]
                    token_df.columns = ["Thời gian", "Model", "Prompt", "Candidate", "Total"]
                    # Đảo ngược để hiển thị mới nhất lên trên (tuỳ chọn, nhưng thường table dễ nhìn hơn)
                    token_df = token_df.iloc[::-1].reset_index(drop=True)
                    
                    st.dataframe(token_df, use_container_width=True, height=250)
                    total_tokens = token_df["Total"].sum()
                    st.info(f"**Tổng Token đã dùng:** {total_tokens}")
        except Exception as e:
            st.error(f"Lỗi khi đọc token log: {e}")
    else:
        st.info("Chưa có lịch sử dùng token.")

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
            "📹 Video Platforms (YouTube, TikTok)",
            "youtube",
            "tiktok",
            "meetup",
            "linkedin",
            "x",
            "web",
        ]

        if crawl_eventbrite:
            platform_options.append("eventbrite")

        selected_platforms = st.multiselect(
            "Nền tảng",
            platform_options,
            default=["📹 Video Platforms (YouTube, TikTok)", "meetup", "linkedin", "web"],
            help="Chọn các nền tảng để cào dữ liệu livestream/webinar",
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

        force_recompile = st.checkbox(
            "🔄 Compile lại profile (bỏ qua cache)",
            value=False,
            help="Bất nếu bạn muốn AI phân tích lại goal từ đầu"
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


if "search_data" not in st.session_state:
    st.session_state["search_data"] = None


if search_btn:

    if not goal.strip():
        st.warning("Vui lòng nhập mục tiêu tìm kiếm.")
        st.stop()

    with st.spinner("🤖 AI đang phân tích mục tiêu..."):

        if use_ai_crawl:
            mode = "ai_then_fallback" if ai_mode == "AI then Fallback" else "fallback_only"

            sig = inspect.signature(crawl_livestreams_with_ai)
            kwargs = {
                "per_platform_timeout": 20,
                "cache": bool(enable_cache),
                "cache_ttl": int(cache_ttl),
                "use_headless": bool(use_headless),
                "force_recompile": bool(force_recompile),
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
                agent_result = crawl_livestreams_with_ai(
                    goal,
                    limit,
                    selected_platforms,
                )

        else:
            agent_result = search_livestreams(
                goal,
                limit,
                use_headless=bool(use_headless),
            )

    queries = agent_result.get("queries", [])
    events = agent_result.get("events", [])

    if status_filter != "ALL":
        events = [event for event in events if event.get("status") == status_filter]

    results = []
    progress = st.progress(0)
    status_placeholder = st.empty()
    total = len(events)

    if total == 0:
        st.warning("Không tìm thấy livestream phù hợp.")
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
                status_placeholder.info(f"⏳ Đang xử lý {current}/{total}")

                if enable_ai:
                    try:
                        ai_result = classify_event(
                            event.get("title", ""),
                            event.get("description", ""),
                            goal
                        )
                        event.update(ai_result)
                        
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

        status_placeholder.success(f"✅ Hoàn thành {total} sự kiện")

    # Store search results into session state so button clicks don't clear results!
    st.session_state["search_data"] = {
        "goal": goal,
        "queries": queries,
        "agent_result": agent_result,
        "results": results,
        "ai_mode": ai_mode,
        "mode": mode if use_ai_crawl else "search"
    }


# =====================================
# RENDER RESULTS FROM SESSION STATE
# =====================================
if st.session_state["search_data"] is not None:
    sdata = st.session_state["search_data"]
    s_goal = sdata.get("goal", "")
    queries = sdata.get("queries", [])
    agent_result = sdata.get("agent_result", {})
    results = sdata.get("results", [])

    st.write("### Search Queries")
    st.write(queries)

    used_profile = load_profile(s_goal)
    if used_profile:
        with st.expander("🧠 Thông tin Goal Profile đang dùng", expanded=False):
            st.caption(f"⏰ Compiled lúc: **{used_profile.get('compiled_at', 'N/A')}**")
            col_i, col_t = st.columns(2)
            with col_i:
                st.markdown("**Industries:**")
                st.write(used_profile.get("industries", []))
            with col_t:
                st.markdown("**Topics:**")
                st.write(used_profile.get("topics", []))
            st.markdown(f"**Số search queries:** {len(used_profile.get('search_queries', []))}")
            st.info("💡 Profile này được tái sử dụng, **không tốn thêm token AI**. Bật '🔄 Compile lại profile' nếu muốn cập nhật.")

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

                st.write("---")
                st.write("🤖 **Huấn luyện Mô hình AI (Active Learning):**")
                col_fb1, col_fb2 = st.columns(2)
                event_url = str(event.get('url') or event.get('title'))
                btn_key_good = f"fb_good_{hash(event_url)}"
                btn_key_spam = f"fb_spam_{hash(event_url)}"

                with col_fb1:
                    if st.button("👍 Đúng Tiềm Năng", key=btn_key_good):
                        from ai.spam_classifier import add_user_feedback
                        add_user_feedback(
                            title=event.get("title", ""),
                            description=event.get("description", ""),
                            label=1,
                            url=event_url
                        )
                        st.toast("✅ Đã ghi nhận phản hồi tích cực! Mô hình AI đã được tự động huấn luyện lại (0.1s).", icon="✅")

                with col_fb2:
                    if st.button("👎 Báo Spam / Rác", key=btn_key_spam):
                        from ai.spam_classifier import add_user_feedback
                        add_user_feedback(
                            title=event.get("title", ""),
                            description=event.get("description", ""),
                            label=0,
                            url=event_url
                        )
                        # Xóa thẻ kết quả này khỏi giao diện hiện tại để không phải load lại từ đầu
                        if st.session_state.get("search_data") and "results" in st.session_state["search_data"]:
                            st.session_state["search_data"]["results"] = [
                                item for item in st.session_state["search_data"]["results"]
                                if str(item.get("url") or item.get("title")) != event_url
                            ]
                        st.toast("🚫 Đã học & tự động ẩn kết quả rác khỏi danh sách!", icon="🚫")
                        st.rerun()