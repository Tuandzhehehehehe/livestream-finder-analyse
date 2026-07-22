"""
dashboard/streamlit_app.py — AI Multi-Platform Livestream Finder Dashboard
=============================================================================
Modular Streamlit application for search, benchmarking, auto-run, and active AI learning.
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import inspect
import json
import os
import time
import urllib.parse
import pandas as pd
# pyrefly: ignore [missing-import]
import streamlit as st

from ai.classify import classify_event
from crawler.session_login import login_interactive_gui
from database.livestream_repository import save_event
from services.ai_crawl_tool import crawl_livestreams_with_ai
from services.goal_profile_compiler import delete_profile, load_profile, list_profiles
from services.search_agent import search_livestreams

try:
    from crawler.eventbrite import crawl_eventbrite
except Exception:
    crawl_eventbrite = None

st.set_page_config(page_title="AI Livestream Finder", layout="wide")


# ── Sidebar UI ─────────────────────────────────────────────────────────────
def render_sidebar():
    with st.sidebar:
        st.write("## 🔑 Quản lý Đăng nhập")
        st.caption("Đăng nhập tài khoản X, TikTok hoặc LinkedIn và đóng cửa sổ khi hoàn tất.")

        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("X (Twitter)", use_container_width=True):
                ok, msg = login_interactive_gui("x")
                st.success(msg) if ok else st.error(msg)
        with c2:
            if st.button("TikTok", use_container_width=True):
                ok, msg = login_interactive_gui("tiktok")
                st.success(msg) if ok else st.error(msg)
        with c3:
            if st.button("LinkedIn", use_container_width=True):
                ok, msg = login_interactive_gui("linkedin")
                st.success(msg) if ok else st.error(msg)

        st.write("---")
        st.write("## 📊 Xuất dữ liệu")
        excel_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "livestreams.xlsx"))
        if os.path.exists(excel_path):
            try:
                with open(excel_path, "rb") as f:
                    st.download_button("📥 Tải xuống Excel", f.read(), file_name="livestreams.xlsx", use_container_width=True, key="sidebar_excel")
            except Exception as e:
                st.error(f"Lỗi Excel: {e}")
        else:
            st.info("Chưa có dữ liệu Excel.")

        st.write("---")
        st.write("## 🧠 Goal Profiles")
        profiles = list_profiles()
        if profiles:
            for p in profiles:
                col_p, col_del = st.columns([3, 1])
                with col_p:
                    st.markdown(f"**{p['goal']}**  \n⏰ {p['compiled_at'][:16]}")
                with col_del:
                    if st.button("🗑️", key=f"del_{p['file']}"):
                        delete_profile(p['goal'])
                        st.rerun()
        else:
            st.info("Chưa có profile nào.")

        st.write("---")
        st.write("## ⚙️ Auto-Run")
        ar_interval = st.number_input("Interval (giờ)", min_value=0.5, max_value=72.0, value=24.0, step=0.5, key="ar_interval")
        ar_platforms_all = ["youtube", "meetup", "linkedin", "web"] + (["eventbrite"] if crawl_eventbrite else [])
        ar_platforms = st.multiselect("Platforms", ar_platforms_all, default=["meetup", "linkedin"], key="ar_platforms")

        col_a1, col_a2 = st.columns(2)
        ar_classify = col_a1.checkbox("Auto-Classify", value=True, key="ar_classify")
        ar_comment = col_a2.checkbox("Auto-Comment", value=False, key="ar_comment")

        if st.button("▶️ Chạy thủ công ngay", use_container_width=True, key="manual_auto_run"):
            with st.spinner("🤖 Đang crawl tất cả Goal Profiles..."):
                try:
                    from services.auto_runner import run_once
                    summary = run_once(platforms=ar_platforms or None, auto_classify=ar_classify, auto_comment=ar_comment)
                    st.success(f"✅ Hoàn tất! {summary['total_new']} mới | {summary['total_skipped']} bỏ qua")
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi: {e}")

        st.write("---")
        st.write("## 🪙 Lịch sử Token AI")
        token_log = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "token_usage.log"))
        if os.path.exists(token_log):
            try:
                records = []
                with open(token_log, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            d = json.loads(line)
                            d["time"] = time.strftime('%H:%M:%S', time.localtime(d.get("timestamp")))
                            records.append(d)
                        except Exception:
                            pass
                if records:
                    df = pd.DataFrame(records)[["time", "model", "prompt_tokens", "candidate_tokens", "total_tokens"]].iloc[::-1]
                    df.columns = ["Thời gian", "Model", "Prompt", "Candidate", "Total"]
                    st.dataframe(df.head(20), use_container_width=True, height=200)
                    st.info(f"**Tổng Token:** {df['Total'].sum():,}")
            except Exception:
                pass


# ── Benchmark Tab ─────────────────────────────────────────────────────────
def render_benchmark_tab():
    st.header("⚡ Crawler Performance & Token Waste Benchmark")
    st.caption("Đánh giá độ trễ, sản lượng và lượng Token lãng phí theo nền tảng.")

    c1, c2 = st.columns([2, 1])
    bm_goal = c1.text_input("Mục tiêu Benchmark", value="AI in HR", key="bm_goal")
    bm_limit = c2.number_input("Số lượng / platform", min_value=1, max_value=50, value=10, key="bm_limit")

    bm_opts = ["youtube", "meetup", "web", "linkedin", "x", "tiktok"] + (["eventbrite"] if crawl_eventbrite else [])
    bm_platforms = st.multiselect("Nền tảng benchmark", bm_opts, default=bm_opts, key="bm_platforms")

    o1, o2, o3 = st.columns(3)
    bm_classify = o1.checkbox("Classify AI", value=True, key="bm_classify")
    bm_comment = o2.checkbox("Comment AI", value=True, key="bm_comment")
    bm_cache = o3.checkbox("Dùng Cache", value=False, key="bm_cache")

    if st.button("🚀 Bắt đầu Benchmark", type="primary", use_container_width=True, key="run_bm"):
        with st.spinner("⚡ Đang tính toán chỉ số Benchmark..."):
            try:
                from services.benchmarker import BenchmarkRunner
                runner = BenchmarkRunner(
                    goal=bm_goal, platforms=bm_platforms or None, limit=bm_limit,
                    use_ai_classify=bm_classify, use_ai_comment=bm_comment, use_cache=bm_cache,
                )
                report = runner.run()
                st.session_state["last_benchmark_report"] = report
                st.success("✅ Hoàn tất Benchmark!")
            except Exception as e:
                st.error(f"Lỗi Benchmark: {e}")

    report = st.session_state.get("last_benchmark_report")
    if report:
        st.write("---")
        st.subheader("📊 Kết quả Benchmark Gần Nhất")
        om, tm = report.get("overall_metrics", {}), report.get("token_metrics", {})

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Thời gian", f"{report.get('duration_seconds', 0)}s")
        m2.metric("Leads chất lượng", f"{om.get('useful_leads_saved', 0)}")
        m3.metric("Tổng Token", f"{tm.get('total_tokens_consumed', 0):,}")
        m4.metric("Lãng phí Token", f"{tm.get('token_waste_percentage', 0)}%", delta=f"-{tm.get('wasted_tokens', 0):,} tokens", delta_color="inverse")

        pb = report.get("platform_breakdown", {})
        if pb:
            df_pb = pd.DataFrame.from_dict(pb, orient="index").reset_index().rename(columns={
                "index": "Nền tảng", "latency_seconds": "Độ trễ (s)", "raw_count": "Sự kiện thô",
                "dedup_count": "Sau Dedup", "scored_count": "Đạt Điểm", "avg_score": "Điểm TB", "throughput_items_per_sec": "Tốc độ (sps)"
            })
            st.dataframe(df_pb[["Nền tảng", "Độ trễ (s)", "Sự kiện thô", "Sau Dedup", "Đạt Điểm", "Điểm TB", "Tốc độ (sps)"]], use_container_width=True)
            st.bar_chart(df_pb.set_index("Nền tảng")[["Độ trễ (s)"]])

        wb = tm.get("waste_breakdown", {})
        if wb:
            w1, w2, w3 = st.columns(3)
            w1.metric("Lãng phí Score < 20", f"{wb.get('low_relevance_waste', 0):,} tokens")
            w2.metric("Lãng phí Trùng DB", f"{wb.get('duplicate_waste', 0):,} tokens")
            w3.metric("Lãng phí Sự kiện cũ", f"{wb.get('expired_time_waste', 0):,} tokens")

    st.write("---")
    st.subheader("📜 Báo cáo Benchmark đã lưu")
    try:
        from services.benchmarker import list_benchmark_reports
        past = list_benchmark_reports(10)
        if past:
            df_past = pd.DataFrame([{
                "Tên file": r.get("_filename", ""),
                "Thời gian": r.get("timestamp", "")[:19].replace("T", " "),
                "Goal": r.get("goal", ""),
                "Thời gian (s)": r.get("duration_seconds", 0),
                "Tổng Token": r.get("token_metrics", {}).get("total_tokens_consumed", 0),
                "Lãng phí (%)": r.get("token_metrics", {}).get("token_waste_percentage", 0),
            } for r in past])
            st.dataframe(df_past, use_container_width=True)
    except Exception as e:
        st.error(f"Lỗi báo cáo: {e}")


# ── Search Tab ────────────────────────────────────────────────────────────
def render_search_tab():
    with st.form("search_form"):
        col1, col2 = st.columns([2, 1])
        with col1:
            goal = st.text_area("Bạn muốn tìm khách hàng ở lĩnh vực nào?", placeholder="Ví dụ: AI Automation, SaaS Founder, Fintech Startup", height=180)

        with col2:
            status_filter = st.selectbox("Trạng thái", ["ALL", "LIVE", "UPCOMING", "COMPLETED"])
            enable_ai = st.checkbox("Đánh giá bằng AI", value=False)
            use_ai_crawl = st.checkbox("Sử dụng AI Crawl Tool", value=True)
            ai_mode = st.selectbox("Chế độ AI / Fallback", ["AI then Fallback", "Fallback only"], index=0)

            plat_opts = ["youtube", "meetup", "x", "tiktok", "linkedin", "web"] + (["eventbrite"] if crawl_eventbrite else [])
            selected_platforms = st.multiselect("Nền tảng", plat_opts, default=["linkedin"] if "linkedin" in plat_opts else plat_opts)

            enable_cache = st.checkbox("Enable per-platform cache", value=True)
            cache_ttl = st.number_input("Cache TTL (seconds)", min_value=0, max_value=86400, value=300)
            use_headless = st.checkbox("Use headless browser for X/TikTok/LinkedIn", value=False)
            force_recompile = st.checkbox("🔄 Compile lại profile (bỏ qua cache)", value=False)
            limit = st.number_input("Số lượng", min_value=1, max_value=100, value=20)

            search_btn = st.form_submit_button("🔍 Tìm kiếm", use_container_width=True)

    if st.button("Xoá cache nền tảng"):
        cache_db = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "platform_cache.sqlite"))
        if os.path.exists(cache_db):
            os.remove(cache_db)
            st.success("Đã xóa cache nền tảng.")

    if "search_data" not in st.session_state:
        st.session_state["search_data"] = None

    if search_btn:
        if not goal.strip():
            st.warning("Vui lòng nhập mục tiêu tìm kiếm.")
            st.stop()

        with st.spinner("🤖 AI đang phân tích mục tiêu..."):
            if use_ai_crawl:
                mode = "ai_then_fallback" if ai_mode == "AI then Fallback" else "fallback_only"
                agent_result = crawl_livestreams_with_ai(
                    goal, limit, platforms=selected_platforms, mode=mode,
                    per_platform_timeout=20, cache=bool(enable_cache), cache_ttl=int(cache_ttl),
                    use_headless=bool(use_headless), force_recompile=bool(force_recompile),
                )
            else:
                agent_result = search_livestreams(goal, limit, use_headless=bool(use_headless))

        queries = agent_result.get("queries", [])
        events = agent_result.get("events", [])

        if status_filter != "ALL":
            events = [e for e in events if e.get("status") == status_filter]

        results = []
        if events:
            progress = st.progress(0)
            status_ph = st.empty()
            total = len(events)

            for index, event in enumerate(events):
                status_ph.info(f"⏳ Đang xử lý {index + 1}/{total}")
                if enable_ai and event.get("_match_score", 0) >= 15:
                    try:
                        orig_match = event.get("_match_score", event.get("score", 0))
                        classification = classify_event(event.get("title", ""), event.get("description", ""), goal)
                        event.update(classification)
                        # Bảo lưu điểm tối đa từ Relevance Engine (MiniLM / Cross-Encoder / Keyword)
                        final_s = max(orig_match, int(event.get("score", 0)))
                        event["score"] = final_s
                        event["priority"] = "High" if final_s >= 80 else ("Medium" if final_s >= 50 else "Low")

                        from ai.comments import generate_comments
                        comments = generate_comments(event.get("title", ""), event.get("description", ""), goal)
                        if comments:
                            event["suggested_comment"] = " | ".join(comments)
                    except Exception as e:
                        st.warning(f"AI Error: {e}")

                save_event(event)
                results.append(event)
                progress.progress((index + 1) / total)

            status_ph.success(f"✅ Hoàn thành {total} sự kiện")

        st.session_state["search_data"] = {
            "goal": goal,
            "queries": queries,
            "agent_result": agent_result,
            "results": results,
            "ai_mode": ai_mode,
        }

    # Render persisted search results
    if st.session_state.get("search_data") is not None:
        sdata = st.session_state["search_data"]
        s_goal = sdata.get("goal", "")
        queries = sdata.get("queries", [])
        results = sdata.get("results", [])

        st.write("### Search Queries", queries)

        profile = load_profile(s_goal)
        if profile:
            with st.expander("🧠 Thông tin Goal Profile đang dùng", expanded=False):
                st.caption(f"⏰ Compiled: {profile.get('compiled_at', 'N/A')}")
                st.markdown(f"**Industries:** {profile.get('industries', [])}")
                st.markdown(f"**Topics:** {profile.get('topics', [])}")

        if not results:
            st.warning("Không tìm thấy livestream phù hợp.")
            return

        # OSINT Google Dorking Links
        st.write("---")
        st.write("## 🌍 Google Dorking (OSINT)")
        q1 = urllib.parse.quote_plus(f'site:linkedin.com/events/ "{s_goal}"')
        q2 = urllib.parse.quote_plus(f'site:linkedin.com/posts/ "{s_goal}" (livestream OR webinar OR "virtual event")')
        st.markdown(f"- [Sự kiện LinkedIn](https://www.google.com/search?q={q1})")
        st.markdown(f"- [Bài đăng Webinar LinkedIn](https://www.google.com/search?q={q2})")

        # Results Table & Expanders
        st.write("---")
        st.write("## KẾT QUẢ")
        df = pd.DataFrame(results)
        cols = [c for c in ["title", "platform", "status", "industry", "buyer_persona", "score", "priority", "url"] if c in df.columns]
        st.dataframe(df[cols], use_container_width=True)

        st.write("## CHI TIẾT")
        icons = {"YouTube": "📺", "Meetup": "🤝", "Eventbrite": "🎟️", "LinkedIn": "💼", "TikTok": "🎵", "X": "🐦"}
        for event in results:
            icon = icons.get(event.get("platform"), "📌")
            with st.expander(f"{icon} {event.get('title')}"):
                st.write(f"**Platform:** {event.get('platform')} | **Status:** {event.get('status')} | **Score:** {event.get('score')}")
                st.write(f"**Industry:** {event.get('industry')} | **Buyer Persona:** {event.get('buyer_persona')}")
                st.write(f"**Language:** {event.get('language')} | **Priority:** {event.get('priority')}")
                st.write(f"**Reason:** {event.get('reason')}")
                st.write(f"**URL:** {event.get('url')}")
                st.write(f"**Suggested Comment:** {event.get('suggested_comment')}")

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
                        if st.session_state.get("search_data") and "results" in st.session_state["search_data"]:
                            st.session_state["search_data"]["results"] = [
                                item for item in st.session_state["search_data"]["results"]
                                if str(item.get("url") or item.get("title")) != event_url
                            ]
                        st.toast("🚫 Đã học & tự động ẩn kết quả rác khỏi danh sách!", icon="🚫")
                        st.rerun()


# ── AI Provider & Token Tracker Tab ──────────────────────────────────────
def render_ai_status_tab():
    st.header("🤖 AI Providers & Token Usage Tracker")
    st.caption("Kiểm tra kết nối các AI Provider (Gemini, Groq, OpenAI) và theo dõi lượng Token tiêu thụ theo thời gian thực.")

    # 1. AI Provider Status
    st.subheader("🔑 Trạng thái AI Provider APIs")
    col_g, col_gr, col_o = st.columns(3)

    from dotenv import load_dotenv
    load_dotenv(override=True)
    gemini_key = os.getenv("GEMINI_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    with col_g:
        st.metric("Gemini API", "Hoạt động ✅" if gemini_key else "Chưa cấu hình ❌")
        if gemini_key:
            st.caption(f"Key: {gemini_key[:8]}...{gemini_key[-4:]}")

    with col_gr:
        st.metric("Groq API (Llama-3.3)", "Hoạt động ✅" if groq_key else "Chưa cấu hình ❌")
        if groq_key:
            st.caption(f"Key: {groq_key[:8]}...{groq_key[-4:]}")

    with col_o:
        st.metric("OpenAI API (GPT-4o)", "Hoạt động ✅" if openai_key else "Chưa cấu hình ❌")
        if openai_key:
            st.caption(f"Key: {openai_key[:8]}...{openai_key[-4:]}")

    st.write("---")

    # 2. Token Usage Statistics
    st.subheader("🪙 Lịch sử & Thống kê Token tiêu thụ")
    token_log = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "token_usage.log"))

    if os.path.exists(token_log):
        records = []
        try:
            import time as _time
            with open(token_log, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        d = json.loads(line)
                        d["time"] = _time.strftime("%Y-%m-%d %H:%M:%S", _time.localtime(d.get("timestamp")))
                        records.append(d)
                    except Exception:
                        pass
        except Exception as e:
            st.error(f"Lỗi đọc log token: {e}")

        if records:
            df = pd.DataFrame(records)
            total_tokens = int(df["total_tokens"].sum()) if "total_tokens" in df else 0
            prompt_tokens = int(df["prompt_tokens"].sum()) if "prompt_tokens" in df else 0
            candidate_tokens = int(df["candidate_tokens"].sum()) if "candidate_tokens" in df else 0

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Tổng Request AI", f"{len(df):,}")
            m2.metric("Prompt Tokens", f"{prompt_tokens:,}")
            m3.metric("Candidate Tokens", f"{candidate_tokens:,}")
            m4.metric("TỔNG TOKENS", f"{total_tokens:,}")

            st.write("### 📜 Lịch sử chi tiết lượt gọi AI mới nhất")
            display_df = df[["time", "model", "category", "prompt_tokens", "candidate_tokens", "total_tokens"]].iloc[::-1]
            display_df.columns = ["Thời gian", "Model / Provider", "Mục đích (Category)", "Prompt", "Candidate", "Total Tokens"]
            st.dataframe(display_df.head(100), use_container_width=True, height=350)
        else:
            st.info("Chưa có ghi nhận sử dụng token nào trong file log.")
    else:
        st.info("Chưa có file log token (`data/token_usage.log`). Hãy thực hiện lượt tìm kiếm AI đầu tiên!")


# ── Main Entrypoint ───────────────────────────────────────────────────────
def main():
    render_sidebar()
    st.title("🎯 AI Multi-Platform Livestream Finder")
    st.caption("Tìm livestream, webinar, workshop, networking event bằng AI")

    tab_search, tab_benchmark, tab_ai = st.tabs([
        "🔍 Tìm kiếm Livestream", 
        "⚡ Benchmark & Token Waste", 
        "🤖 Trạng thái AI & Token Tracker"
    ])
    with tab_search:
        render_search_tab()
    with tab_benchmark:
        render_benchmark_tab()
    with tab_ai:
        render_ai_status_tab()


if __name__ == "__main__":
    main()
