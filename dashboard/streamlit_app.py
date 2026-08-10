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
import sys
import time
import urllib.parse

# Đảm bảo project root nằm trong sys.path (Streamlit có thể chạy từ thư mục khác)
_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
import pandas as pd
# pyrefly: ignore [missing-import]
import streamlit as st

from ai.classify import classify_event
from crawler.session_login import login_interactive_gui
from database.channel_repository import get_channel_summary
from database.livestream_repository import get_summary_stats, save_event
from services.ai_crawl_tool import crawl_livestreams_with_ai
from services.auto_runner import read_log_entries
from services.goal_profile_compiler import delete_profile, load_profile, list_profiles
from services.search_agent import search_livestreams
from services.channel_runner import enqueue_channels_from_events, export_ranking, refresh_channel_scores, run_channel_pipeline

st.set_page_config(page_title="AI Livestream Finder", layout="wide")


# ── Sidebar UI ─────────────────────────────────────────────────────────────
def render_sidebar():
    with st.sidebar:
        st.write("## 🔑 Quản lý Đăng nhập")
        st.caption("Đăng nhập tài khoản TikTok và đóng cửa sổ khi hoàn tất.")

        if st.button("TikTok", use_container_width=True):
            ok, msg = login_interactive_gui("tiktok")
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
        ar_platforms_all = ["youtube", "tiktok", "web"]
        ar_platforms = st.multiselect("Platforms", ar_platforms_all, default=["youtube", "tiktok"], key="ar_platforms")

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
    st.header("⚡ Agent Evaluation & Benchmark Center")
    st.caption("Khung đánh giá toàn diện năng lực Agent: 4 Trụ Cột Kỹ Thuật + Hội Đồng Giám Khảo AI Độc Lập (G-Eval / NDCG).")

    tab_custom, tab_golden, tab_hf = st.tabs([
        "🎯 Đánh Giá Mục Tiêu Cụ Thể (Custom Goal)",
        "🏛️ Khảo Sát Bộ Đề Chuẩn (Golden Dataset)",
        "🤗 So Sánh Chuẩn Hugging Face (BEIR & MS MARCO)"
    ])

    # ── SUB-TAB 1: CUSTOM GOAL BENCHMARK ──────────────────────────────────────
    with tab_custom:
        st.markdown("#### 🎯 Đánh Giá Hiệu Năng Agent Cho Mục Tiêu Bạn Chọn")
        st.caption("Nhập bất kỳ chủ đề nào (ví dụ: *'Charity & Non-Profit'*, *'AI in HR'*, *'Fintech'*) để cào dữ liệu thực tế và chấm điểm qua 4 trụ cột + Giám khảo AI.")

        c1, c2 = st.columns([2, 1])
        bm_goal = c1.text_input("Mục tiêu Benchmark", value="Charity & Non-profit Fundraising", key="bm_goal_custom")
        bm_limit = c2.number_input("Số lượng / platform", min_value=1, max_value=50, value=10, key="bm_limit_custom")

        bm_opts = ["youtube", "tiktok", "web"]
        bm_platforms = st.multiselect("Nền tảng benchmark", bm_opts, default=bm_opts, key="bm_platforms_custom")

        o1, o2, o3 = st.columns(3)
        bm_classify = o1.checkbox("Classify AI", value=True, key="bm_classify_custom")
        bm_comment = o2.checkbox("Comment AI", value=True, key="bm_comment_custom")
        bm_cache = o3.checkbox("Dùng Cache", value=False, key="bm_cache_custom")

        if st.button("🚀 Bắt Đầu Đánh Giá Mục Tiêu Này", type="primary", use_container_width=True, key="run_bm_custom"):
            if not bm_goal.strip():
                st.warning("Vui lòng nhập mục tiêu cần đánh giá.")
            else:
                with st.spinner(f"⚡ Đang cào dữ liệu và chấm điểm cho mục tiêu '{bm_goal}'..."):
                    try:
                        from services.benchmarker import BenchmarkRunner
                        runner = BenchmarkRunner(
                            goal=bm_goal, platforms=bm_platforms or None, limit=bm_limit,
                            use_ai_classify=bm_classify, use_ai_comment=bm_comment, use_cache=bm_cache,
                        )
                        report = runner.run()
                        st.session_state["last_benchmark_report"] = report
                        st.success(f"✅ Đã hoàn tất đánh giá mục tiêu '{bm_goal}'!")
                    except Exception as e:
                        st.error(f"Lỗi Benchmark: {e}")

        report = st.session_state.get("last_benchmark_report")
        if report and report.get("goal"):
            st.write("---")
            st.subheader(f"📊 Kết Quả Đánh Giá Mục Tiêu: '{report.get('goal')}'")

            # Third-Party Judge Score Banner
            tp_judge = report.get("third_party_judge", {})
            if tp_judge:
                j_score = tp_judge.get("g_eval_score", 0)
                j_ndcg = tp_judge.get("ndcg_at_5", 0)
                st.markdown("#### 🏛️ Điểm Số Từ Hội Đồng Giám Khảo Độc Lập (LLM-as-a-Judge)")
                col_j1, col_j2 = st.columns(2)
                col_j1.metric("G-Eval Judge Score", f"{j_score} / 100", help="Điểm chất lượng & độ đúng ngành do Giám khảo AI độc lập chấm")
                col_j2.metric("NDCG@5 (Chuẩn Tìm Kiếm)", f"{j_ndcg} / 1.000", help="Độ chuẩn xác khi xếp các livestream tốt nhất lên Top 5")

            em = report.get("evaluation_metrics", {})
            p1 = em.get("pillar_1_scraper_performance", {})
            p2 = em.get("pillar_2_relevance_quality", {})
            p3 = em.get("pillar_3_token_economy", {})
            p4 = em.get("pillar_4_lead_actionability", {})

            col_p1, col_p2 = st.columns(2)
            with col_p1:
                st.markdown("##### 1️⃣ Hiệu Năng Scraper (Playwright)")
                k1, k2 = st.columns(2)
                k1.metric("Live Precision", f"{p1.get('live_precision_rate', 0)}%", help="Tỷ lệ livestream thực tế (không bị lẫn video tĩnh)")
                k2.metric("Độ Đầy Đủ Dữ Liệu", f"{p1.get('field_completeness_rate', 0)}%", help="Tỷ lệ các trường Title, Channel, Status không bị null")
                k3, k4 = st.columns(2)
                k3.metric("Tốc độ bóc tách", f"{p1.get('throughput_items_per_sec', 0)} sps")
                k4.metric("Độ trễ trung bình", f"{p1.get('avg_latency_per_item_sec', 0)}s / item")

            with col_p2:
                st.markdown("##### 2️⃣ Chất Lượng Phù Hợp & AI (Relevance)")
                k5, k6 = st.columns(2)
                k5.metric("Precision@5", f"{p2.get('precision_at_5', 0)}%")
                k6.metric("Spam Leakage", f"{p2.get('spam_leakage_rate', 0)}%", delta=f"{p2.get('spam_leakage_rate', 0)}%", delta_color="inverse")
                k7, k8 = st.columns(2)
                k7.metric("MRR (Best Match Rank)", f"{p2.get('mean_reciprocal_rank', 0)}")
                k8.metric("Độ Đúng Trạng Thái", f"{p2.get('status_accuracy_rate', 0)}%")

            col_p3, col_p4 = st.columns(2)
            with col_p3:
                st.markdown("##### 3️⃣ Kinh Tế Token & Tiết Kiệm")
                k9, k10 = st.columns(2)
                k9.metric("Hiệu Quả Token", f"{p3.get('token_efficiency_percentage', 0)}%")
                k10.metric("Lãng Phí Token", f"{p3.get('token_waste_percentage', 0)}%", delta=f"-{p3.get('wasted_tokens', 0):,} tokens", delta_color="inverse")

            with col_p4:
                st.markdown("##### 4️⃣ Tính Hành Động Của Lead")
                k13, k14 = st.columns(2)
                k13.metric("Tỷ Lệ Lead Ưu Tiên Cao", f"{p4.get('high_priority_ratio', 0)}%")
                k14.metric("Điểm Tiềm Năng TB", f"{p4.get('avg_lead_score', 0)} / 100")

            # Bảng chi tiết từng video kèm nhận xét của Giám khảo AI
            eval_items = tp_judge.get("evaluated_items", [])
            if eval_items:
                st.write("---")
                st.markdown(f"#### 🔍 Chi Tiết Từng Video Tìm Được & Nhận Xét Giám Khảo Cho: '{report.get('goal')}'")
                df_ev_items = pd.DataFrame([{
                    "Hạng": it.get("rank", 0),
                    "Tiêu đề video": it.get("title", ""),
                    "Kênh": it.get("channel_name", ""),
                    "Trạng thái": it.get("status", ""),
                    "Điểm Giám Khảo": f"{it.get('judge_score', 0)}/100",
                    "Đúng Ngành?": "✅ Đúng" if it.get("is_relevant") else "❌ Sai",
                    "Là Spam?": "🚨 Rác/Scam" if it.get("is_spam") else "✨ An toàn",
                    "Giám khảo nhận xét": it.get("critique", ""),
                } for it in eval_items])
                st.dataframe(df_ev_items, use_container_width=True)

    # ── SUB-TAB 2: GOLDEN BENCHMARK SUITE (15 NGÀNH) ─────────────────────────
    with tab_golden:
        st.markdown("#### 🏛️ Sát Hạch Bộ Đề Chuẩn Quốc Tế (Golden Benchmark Suite)")
        st.caption("Khảo sát toàn diện năng lực của Agent trên 15 bộ đề thi chuẩn đa ngành (B2B SaaS, AI, Fintech, Charity, DevOps, Cybersecurity, v.v.) theo chuẩn BEIR/GAIA.")

        gc1, gc2 = st.columns([2, 1])
        num_golden = gc1.slider("Số lượng bài test trong Golden Dataset", min_value=1, max_value=15, value=5, key="num_golden_slider")
        use_judge_llm = gc2.checkbox("Bật LLM-as-a-Judge (Chấm điểm mù)", value=True, key="use_judge_llm_cb")

        if st.button("🏛️ Bắt Đầu Thi Sát Hạch Toàn Diện", type="secondary", use_container_width=True, key="run_golden_btn"):
            with st.spinner("🏛️ Ban giám khảo AI đang chấm điểm độc lập trên bộ đề Golden Dataset..."):
                try:
                    from services.golden_evaluator import GoldenDatasetEvaluator
                    g_evaluator = GoldenDatasetEvaluator(
                        max_test_cases=int(num_golden),
                        items_per_query=5,
                        use_llm_judge=use_judge_llm,
                    )
                    g_report = g_evaluator.run_evaluation()
                    st.session_state["last_golden_report"] = g_report
                    st.success("✅ Hoàn tất bài thi sát hạch trên Golden Dataset!")
                except Exception as ge_err:
                    st.error(f"Lỗi Golden Evaluation: {ge_err}")

        g_rep = st.session_state.get("last_golden_report")
        if g_rep:
            ob = g_rep.get("overall_benchmarks", {})
            st.markdown("#### 🏆 Bảng Điểm Chuẩn Quốc Tế Của Toàn Bộ Bài Thi")

            j1, j2, j3, j4 = st.columns(4)
            j1.metric("G-Eval Score", f"{ob.get('g_eval_judge_score', 0)} / 100", help="Điểm trung bình theo tiêu chí G-Eval từ ban giám khảo độc lập")
            j2.metric("NDCG@5 (Chuẩn Search)", f"{ob.get('ndcg_at_5', 0)} / 1.000", help="Độ chuẩn xác khi xếp kết quả tốt nhất lên đầu")
            j3.metric("MRR", f"{ob.get('mrr_mean_reciprocal_rank', 0)}", help="Vị trí trung bình của kết quả đúng đầu tiên")
            j4.metric("MAP", f"{ob.get('map_mean_average_precision', 0)}", help="Độ chính xác trung bình toàn bộ bài test")

            t_breakdown = g_rep.get("test_case_breakdown", [])
            if t_breakdown:
                st.markdown("#### 📋 Chi tiết kết quả từng bài test trong đề thi")
                df_tests = pd.DataFrame([{
                    "Mã bài test": tb.get("test_id", ""),
                    "Mục tiêu (Goal)": tb.get("goal", ""),
                    "Lĩnh vực": tb.get("category", ""),
                    "NDCG@5": tb.get("ndcg_at_5", 0),
                    "MRR": tb.get("mrr", 0),
                    "Thời gian (s)": tb.get("latency_seconds", 0),
                    "Số kết quả": tb.get("items_retrieved", 0),
                } for tb in t_breakdown])
                st.dataframe(df_tests, use_container_width=True)

    # ── SUB-TAB 3: HUGGING FACE UNIVERSAL BENCHMARK ──────────────────────────
    with tab_hf:
        st.markdown("#### 🤗 Đánh Giá Trực Tiếp Trên Dataset Chuẩn Của Hugging Face")
        st.caption("Kết nối trực tiếp với Hugging Face Hub (BEIR / MS MARCO) để so sánh Agent của bạn với các mô hình tìm kiếm chuẩn quốc tế.")

        hf_col1, hf_col2 = st.columns([2, 1])
        hf_dataset_choice = hf_col1.selectbox(
            "Chọn Dataset chuẩn trên Hugging Face Hub",
            [
                "BeIR/fiqa (Finance & FinTech Search Benchmark)",
                "BeIR/scifact (AI & Science Claims Search Benchmark)",
                "BeIR/trec-covid (Healthcare & Medical Search Benchmark)",
                "microsoft/ms_marco (Microsoft Universal Web Search Benchmark)",
                "BeIR/quora (Semantic Search & Duplicate Retrieval)",
            ],
            index=0,
            key="hf_ds_choice",
        )
        hf_dataset_key = hf_dataset_choice.split(" ")[0]
        hf_query_limit = hf_col2.number_input("Số lượng queries kiểm thử", min_value=1, max_value=20, value=3, key="hf_q_limit")

        if st.button("🤗 Tải Dataset Từ Hugging Face & Chấm Điểm So Sánh Trực Tiếp", type="primary", use_container_width=True, key="run_hf_btn"):
            with st.spinner(f"🤗 Đang kết nối Hugging Face Hub ({hf_dataset_key}) và chấm điểm so sánh..."):
                try:
                    from services.huggingface_evaluator import HuggingFaceBenchmarkEvaluator
                    hf_eval = HuggingFaceBenchmarkEvaluator(
                        dataset_name=hf_dataset_key,
                        max_queries=int(hf_query_limit),
                    )
                    hf_report = hf_eval.evaluate_agent_against_hf_benchmark()
                    st.session_state["last_hf_report"] = hf_report
                    st.success(f"✅ Đã hoàn tất đánh giá trên dataset Hugging Face: {hf_dataset_key}!")
                except Exception as hf_err:
                    st.error(f"Lỗi Hugging Face Benchmark: {hf_err}")

        hf_rep = st.session_state.get("last_hf_report")
        if hf_rep:
            st.write("---")
            st.markdown(f"### 🏆 Bảng So Sánh Agent Của Bạn vs Các Chuẩn Quốc Tế ({hf_rep.get('dataset_name')})")

            am = hf_rep.get("agent_metrics", {})
            c_h1, c_h2, c_h3, c_h4 = st.columns(4)
            c_h1.metric("NDCG@10 (Agent của bạn)", f"{am.get('ndcg_at_10', 0)} / 1.000")
            c_h2.metric("So với BM25 Baseline", f"+{am.get('improvement_vs_bm25_pct', 0)}%", delta=f"+{am.get('improvement_vs_bm25_pct', 0)}%", help="Tỷ lệ vượt trội so với chuẩn tìm kiếm BM25 truyền thống")
            c_h3.metric("MRR@10", f"{am.get('mrr_at_10', 0)}")
            c_h4.metric("MAP@10", f"{am.get('map_at_10', 0)}")

            # Bảng so sánh trực tiếp
            ub = hf_rep.get("universal_baseline_comparison", {})
            if ub:
                st.markdown("#### 📊 Bảng So Sánh Các Mô Hình & Phương Pháp:")
                df_compare = pd.DataFrame([{
                    "Phương pháp / Mô hình": k.replace("_", " "),
                    "Điểm NDCG@10": v.get("ndcg_at_10", 0),
                    "Nguồn / Chuẩn đối chiếu": v.get("source", ""),
                } for k, v in ub.items()])
                st.dataframe(df_compare, use_container_width=True)
                st.bar_chart(df_compare.set_index("Phương pháp / Mô hình")[["Điểm NDCG@10"]])

            q_breakdown = hf_rep.get("query_breakdown", [])
            if q_breakdown:
                st.markdown("#### 📋 Chi tiết từng bài test trên Hugging Face:")
                df_q = pd.DataFrame([{
                    "Mã Query": qb.get("query_id", ""),
                    "Câu hỏi / Mục tiêu": qb.get("query", ""),
                    "NDCG@10": qb.get("ndcg_at_10", 0),
                    "MRR@10": qb.get("mrr_at_10", 0),
                    "Kết quả Top 1 chính xác?": "✅ Đúng" if qb.get("top_1_is_relevant") else "❌ Sai",
                    "Văn bản Top 1 tìm được": qb.get("top_1_text", ""),
                } for qb in q_breakdown])
                st.dataframe(df_q, use_container_width=True)

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
                "Live Precision (%)": r.get("evaluation_metrics", {}).get("pillar_1_scraper_performance", {}).get("live_precision_rate", 100.0),
                "Precision@5 (%)": r.get("evaluation_metrics", {}).get("pillar_2_relevance_quality", {}).get("precision_at_5", 100.0),
                "Tổng Token": r.get("token_metrics", {}).get("total_tokens_consumed", 0),
                "Lãng phí (%)": r.get("token_metrics", {}).get("token_waste_percentage", 0),
            } for r in past])
            st.dataframe(df_past, width="stretch")
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

            plat_opts = ["youtube", "tiktok", "web"]
            selected_platforms = st.multiselect("Nền tảng", plat_opts, default=["youtube", "tiktok"])

            yt_mode_choice = st.selectbox("Bộ lọc YouTube (Playwright)", ["Tất cả (Live & Upcoming)", "Chỉ Live đang phát", "Chỉ Sắp diễn ra (Upcoming)"], index=0)
            yt_mode_val = "all" if "Tất cả" in yt_mode_choice else ("live" if "Chỉ Live" in yt_mode_choice else "upcoming")

            enable_cache = st.checkbox("Enable per-platform cache", value=True)
            cache_ttl = st.number_input("Cache TTL (seconds)", min_value=0, max_value=86400, value=300)
            use_headless = st.checkbox("Use headless browser for Playwright/TikTok", value=True)
            use_youtube_api = st.checkbox("🔑 Dùng YouTube API (Mặc định: dùng Playwright Scraper)", value=False)
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

        with st.spinner("🤖 AI đang phân tích mục tiêu và cào dữ liệu YouTube..."):
            if use_ai_crawl:
                mode = "ai_then_fallback" if ai_mode == "AI then Fallback" else "fallback_only"
                agent_result = crawl_livestreams_with_ai(
                    goal, limit, platforms=selected_platforms, mode=mode,
                    per_platform_timeout=25, cache=bool(enable_cache), cache_ttl=int(cache_ttl),
                    use_headless=bool(use_headless), force_recompile=bool(force_recompile),
                    use_youtube_api=bool(use_youtube_api), youtube_mode=yt_mode_val,
                )
            else:
                agent_result = search_livestreams(goal, limit, use_headless=bool(use_headless), use_youtube_api=bool(use_youtube_api))

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

            # ── Tự động crawl channel từ events vừa tìm được ─────────────────
            with st.spinner("📡 Đang thu thập thông tin kênh từ kết quả..."):
                ch_sum = enqueue_channels_from_events(results)
            if ch_sum.get("new_urls", 0) > 0:
                st.info(
                    f"📡 AutoChannel: **{ch_sum.get('saved', 0)}** kênh mới lưu | "
                    f"**{ch_sum.get('skipped_existing', 0)}** đã có trong DB | "
                    f"**{ch_sum.get('skipped_crawl', 0)}** bỏ qua"
                )

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
        st.write("---")
        st.write("## 🌍 Google Dorking (OSINT)")
        q1 = urllib.parse.quote_plus(f'site:youtube.com/watch "{s_goal}"')
        st.markdown(f"- [Livestream YouTube](https://www.google.com/search?q={q1})")

        # Results Table & Expanders
        st.write("---")
        st.write("## KẾT QUẢ")
        df = pd.DataFrame(results)
        cols = [c for c in ["title", "platform", "status", "industry", "buyer_persona", "score", "priority", "url"] if c in df.columns]
        st.dataframe(df[cols], width="stretch")

        st.write("## CHI TIẾT")
        icons = {"YouTube": "📺", "TikTok": "🎵", "Web": "🌐"}
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

    # pyrefly: ignore [missing-import]
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


# ── Channel Tab ───────────────────────────────────────────────────────────
def render_channel_tab():
    st.header("📡 Channel Intelligence")
    st.caption(
        "Kênh được tự động thu thập sau mỗi lần tìm kiếm livestream. "
        "Chọn khu vực để xem bảng xếp hạng và đề xuất kênh nổi bật."
    )

    from channel_crawler.region_mapper import list_supported_regions
    REGIONS = list_supported_regions()

    # ── Làm mới điểm số ────────────────────────────────────────────────
    _, c_ref = st.columns([4, 1])
    with c_ref:
        if st.button("🔄 Làm mới CAS", key="ch_refresh_btn", use_container_width=True):
            with st.spinner("Đang tính lại CAS + growth..."):
                r = refresh_channel_scores()
            st.success(f"CAS: {r['cas_updated']} kênh | Growth: {r['growth_updated']} kênh")

    st.write("---")

    # ── Chọn khu vực & chạy pipeline ──────────────────────────────────────
    col1, col2, col3 = st.columns([2, 1, 1])
    target_region = col1.selectbox(
        "🌏 Khu vực",
        REGIONS,
        index=REGIONS.index("VN") if "VN" in REGIONS else 0,
        key="ch_region",
    )
    ch_platform = col2.selectbox(
        "Platform", ["(tất cả)", "youtube", "tiktok"],
        key="ch_filter_platform",
    )
    top_k = col3.number_input("Top K đề xuất", min_value=3, max_value=50, value=10, key="ch_topk")

    min_cas = st.slider("CAS tối thiểu", 0, 100, 20, key="ch_mincas")
    diverse = st.checkbox("🔀 Đa dạng hóa platform (mỗi platform tối đa ceil(top_k/2) kênh)", value=True, key="ch_diverse")

    if st.button("📊 Xem kênh nổi bật", type="primary", key="ch_run_btn", use_container_width=True):
        platform_filter = None if ch_platform == "(tất cả)" else ch_platform
        with st.spinner(f"Đang phân tích khu vực {target_region}..."):
            report = run_channel_pipeline(
                target_region,
                platform=platform_filter,
                refresh_scores=False,  # user tự bấm refresh nếu muốn
                top_k_rank=50,
                top_k_recommend=int(top_k),
                min_cas=float(min_cas),
                diverse=diverse,
            )
        st.session_state["ch_report"] = report

    report = st.session_state.get("ch_report")
    if not report:
        return

    ranking = report.get("ranking", [])
    recs    = report.get("recommendations", [])
    region  = report.get("region", "?")

    # ── Bảng xếp hạng ─────────────────────────────────────────────────────────
    st.write(f"### 🏆 Xếp hạng kênh — {region} ({len(ranking)} kênh)")
    if ranking:
        # ── Metrics summary ────────────────────────────────────────────────────
        rcas_max = max((ch.get("rcas", 0) for ch in ranking), default=0)
        cas_avg  = sum(ch.get("cas", 0) for ch in ranking) / len(ranking)
        plat_dist: dict[str, int] = {}
        for ch in ranking:
            p = (ch.get("platform") or "?").upper()
            plat_dist[p] = plat_dist.get(p, 0) + 1
        plat_str = "  ·  ".join(f"{p} {n}" for p, n in sorted(plat_dist.items()))

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("📋 Tổng kênh",     len(ranking))
        m2.metric("🥇 RCAS cao nhất",  f"{rcas_max:.1f}")
        m3.metric("📊 CAS trung bình", f"{cas_avg:.1f}")
        m4.metric("🌐 Platforms",      plat_str)

        st.write("")

        # ── Build display dataframe ────────────────────────────────────────────
        df_rank = pd.DataFrame([{
            "#":        i + 1,
            "Tier":     ch.get("tier", "?"),
            "Tên kênh": ch.get("channel_name") or ch.get("username") or ch.get("channel_url", "?"),
            "URL":      ch.get("channel_url", "#"),
            "Platform": (ch.get("platform") or "?").upper(),
            "Follower": ch.get("follower_count") or 0,
            "CAS":      round(ch.get("cas", 0), 1),
            "RCAS":     round(ch.get("rcas", 0), 1),
            "Khu vực":  ch.get("region_tag") or ch.get("country") or "–",
        } for i, ch in enumerate(ranking)])

        st.dataframe(
            df_rank[["#", "Tier", "Tên kênh", "URL", "Platform", "Follower", "CAS", "RCAS", "Khu vực"]],
            use_container_width=True,
            height=min(500, 38 + 35 * len(df_rank)),
            column_config={
                "#":        st.column_config.NumberColumn("#", width="small"),
                "Tier":     st.column_config.TextColumn("Tier", width="medium"),
                "Tên kênh": st.column_config.TextColumn("Tên kênh"),
                "URL":      st.column_config.LinkColumn("🔗", display_text="Mở", width="small"),
                "Follower": st.column_config.NumberColumn("Follower", format="%d"),
                "CAS":      st.column_config.ProgressColumn("CAS",  min_value=0, max_value=100, format="%.1f"),
                "RCAS":     st.column_config.ProgressColumn("RCAS", min_value=0, max_value=100, format="%.1f"),
            },
        )

        # ── Bar chart RCAS top 10 ──────────────────────────────────────────────
        top10 = ranking[:10]
        if top10:
            st.write("#### 📊 Top 10 — RCAS & CAS Score")
            chart_data = pd.DataFrame({
                "Kênh": [
                    (ch.get("channel_name") or ch.get("username") or f"#{i+1}")[:25]
                    for i, ch in enumerate(top10)
                ],
                "RCAS": [round(ch.get("rcas", 0), 1) for ch in top10],
                "CAS":  [round(ch.get("cas", 0), 1)  for ch in top10],
            }).set_index("Kênh")
            st.bar_chart(chart_data, color=["#4f8ef7", "#a78bfa"])

        # ── Export buttons ─────────────────────────────────────────────────────
        st.write("")
        ec1, ec2, _ = st.columns([1, 1, 4])
        with ec1:
            csv_data = export_ranking(ranking, fmt="csv")
            st.download_button(
                label="📥 Xuất CSV",
                data=csv_data.encode("utf-8"),
                file_name=f"ranking_{region}.csv",
                mime="text/csv",
                key="ch_export_csv",
                use_container_width=True,
            )
        with ec2:
            json_data = export_ranking(ranking, fmt="json")
            st.download_button(
                label="📥 Xuất JSON",
                data=json_data.encode("utf-8"),
                file_name=f"ranking_{region}.json",
                mime="application/json",
                key="ch_export_json",
                use_container_width=True,
            )
    else:
        st.info("Chưa có kênh nào trong khu vực này. Hãy crawl thêm dữ liệu.")

    # ── Đề xuất nổi bật ───────────────────────────────────────────────────────
    st.write(f"### ⭐ Đề xuất nổi bật — Top {len(recs)}")
    if recs:
        cols_per_row = 2
        for row_start in range(0, len(recs), cols_per_row):
            cols = st.columns(cols_per_row)
            for col_idx, ch in enumerate(recs[row_start: row_start + cols_per_row]):
                with cols[col_idx], st.container(border=True):
                    name = ch.get("channel_name") or ch.get("username") or "?"
                    url  = ch.get("channel_url", "#")
                    rcas = ch.get("rcas", 0)
                    st.markdown(
                        f"**[{name}]({url})**\n\n"
                        f"`{(ch.get('platform') or '?').upper()}` &nbsp;&nbsp; "
                        f"{ch.get('tier', '?')} &nbsp;&nbsp; "
                        f"🌏 {ch.get('region_tag') or ch.get('country') or '?'}"
                    )
                    st.caption(
                        f"Follower: {ch.get('follower_count') or 0:,}  ·  "
                        f"CAS {ch.get('cas', 0):.1f}  ·  RCAS {rcas:.1f}"
                    )
                    st.progress(min(int(rcas), 100), text=f"RCAS {rcas:.1f} / 100")
                    if ch.get("reason"):
                        with st.expander("💡 Lý do đề xuất"):
                            for part in ch["reason"].split("  ·  "):
                                st.markdown(f"- {part.strip()}")
    else:
        st.warning(
            "⚠️ Không có kênh nào đáp ứng ngưỡng hiện tại.\n\n"
            f"🔧 **Gợi ý:** Thử giảm **CAS tối thiểu** xuống (hiện đang là {min_cas}) "
            "hoặc bấm **🔄 Làm mới CAS** rồi chạy lại."
        )


# ── Overview Tab ───────────────────────────────────────────────────────

def render_overview_tab():
    st.header("📋 Tổng quan hệ thống")
    st.caption("Số liệu cập nhật sau mỗi lần tìm kiếm hoặc auto-run. Nhấn F5 để lấy số liệu mới nhất.")

    ev  = get_summary_stats()
    ch  = get_channel_summary()
    log = read_log_entries(20)

    # ── Section 1: Metrics tổng quan ───────────────────────────────────────
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("📊 Tổng Events",   ev["total_events"])
    m2.metric("⭐ Score cao nhất",  ev["top_score"])
    m3.metric("📈 Score TB",        f"{ev['avg_score']:.1f}")
    m4.metric("📡 Tổng Kênh",     ch["total_channels"])
    m5.metric("🏆 CAS cao nhất",  f"{ch['top_cas']:.1f}")
    m6.metric("🔢 Kênh có CAS",    ch["channels_with_score"])

    st.write("")

    # ── Section 2: Livestream breakdown ─────────────────────────────────
    st.write("### 🌐 Livestream Events")
    c_left, c_mid, c_right = st.columns([2, 1, 1])

    with c_left:
        if ev["by_platform"]:
            df_plat = pd.DataFrame(
                list(ev["by_platform"].items()),
                columns=["Platform", "Số lượng"],
            ).set_index("Platform")
            st.write("**Phân bố theo Platform**")
            st.bar_chart(df_plat)
        else:
            st.info("Chưa có dữ liệu.")

    with c_mid:
        st.write("**Priority**")
        if ev["by_priority"]:
            _order = {"High": 0, "Medium": 1, "Low": 2}
            _badge = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}
            for name, count in sorted(ev["by_priority"].items(), key=lambda x: _order.get(x[0], 9)):
                st.metric(f"{_badge.get(name, '⚫')} {name}", count)
        else:
            st.info("Chưa có dữ liệu.")

    with c_right:
        st.write("**Trạng thái**")
        if ev["by_status"]:
            _badge = {"LIVE": "🔴", "UPCOMING": "🟡", "COMPLETED": "✅"}
            for name, count in sorted(ev["by_status"].items()):
                st.metric(f"{_badge.get(name, '⚫')} {name}", count)
        else:
            st.info("Chưa có dữ liệu.")

    st.caption(f"⏰ Event mới nhất lúc: {ev['latest_crawled_at']}")
    st.write("")

    # ── Section 3: Channel Intelligence ────────────────────────────────
    st.write("### 📡 Channel Intelligence")
    cc_left, cc_right = st.columns([2, 1])

    with cc_left:
        if ch["by_platform"]:
            df_ch = pd.DataFrame(
                list(ch["by_platform"].items()),
                columns=["Platform", "Số kênh"],
            ).set_index("Platform")
            st.write("**Kênh theo Platform**")
            st.bar_chart(df_ch)
        else:
            st.info("Chưa có kênh nào.")

    with cc_right:
        st.write("**CAS Stats**")
        st.metric("🏆 CAS cao nhất", f"{ch['top_cas']:.1f}")
        st.metric("📈 CAS trung bình", f"{ch['avg_cas']:.1f}")
        st.metric("🔢 Chưa có CAS", ch["total_channels"] - ch["channels_with_score"])

    st.caption(f"⏰ Kênh mới nhất lúc: {ch['latest_crawled_at']}")
    st.write("")

    # ── Section 4: Auto-Run History ─────────────────────────────────────
    st.write("### ⏳ Lịch sử Auto-Run (20 lần gần nhất)")
    if log:
        df_log = pd.DataFrame([{
            "⏰ Thời gian":   (e.get("timestamp") or "")[:19].replace("T", " "),
            "🎯 Goal":          (e.get("goal") or "")[:60],
            "➕ Mới":           e.get("new_events", "–"),
            "⏭ Bỏ qua":        e.get("skipped", "–"),
            "🔍 Tìm được":      e.get("total_found", "–"),
            "📊 Status":        "✅ OK" if e.get("status") == "ok" else f"❌ {e.get('error', '')[:40]}",
        } for e in log])
        st.dataframe(df_log, use_container_width=True, height=min(500, 38 + 35 * len(df_log)))
    else:
        st.info(
            "💤 Chưa có lịch sử auto-run. "
            "Bấm **▶️ Chạy thủ công ngay** trong sidebar để bắt đầu."
        )


# ── Main Entrypoint ───────────────────────────────────────────────────────
def main():
    render_sidebar()
    st.title("🎯 AI Multi-Platform Livestream Finder")
    st.caption("Tìm livestream, webinar, workshop, networking event bằng AI")

    tab_overview, tab_search, tab_channel, tab_benchmark, tab_ai = st.tabs([
        "📋 Tổng quan",
        "🔍 Tìm kiếm Livestream",
        "📡 Kênh nổi bật",
        "⚡ Benchmark & Token Waste",
        "🤖 Trạng thái AI & Token Tracker",
    ])
    with tab_overview:
        render_overview_tab()
    with tab_search:
        render_search_tab()
    with tab_channel:
        render_channel_tab()
    with tab_benchmark:
        render_benchmark_tab()
    with tab_ai:
        render_ai_status_tab()


if __name__ == "__main__":
    main()
