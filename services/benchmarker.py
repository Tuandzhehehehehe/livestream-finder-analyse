"""
services/benchmarker.py — Crawler & Token Waste Benchmarking Engine
=====================================================================
Benchmarks crawler latency, yield, deduplication, relevance scoring,
AI token usage, and calculates detailed token waste across pipeline stages.
"""

import os
import time
import json
import sqlite3
import hashlib
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from database.livestream_repository import get_event_by_url


# ── Helper to read tokens from log file ──────────────────────────────────────
def get_token_log_entries(since_timestamp: float = 0.0) -> List[Dict[str, Any]]:
    """Đọc các bản ghi token usage từ timestamp chỉ định."""
    log_file = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "data", "token_usage.log")
    )
    if not os.path.exists(log_file):
        return []

    entries = []
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("timestamp", 0) >= since_timestamp:
                        entries.append(entry)
                except Exception:
                    pass
    except Exception:
        pass
    return entries


def summarize_tokens(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Tổng hợp token theo provider, model và category."""
    summary = {
        "prompt_tokens": 0,
        "candidate_tokens": 0,
        "total_tokens": 0,
        "categories": {},
        "models": {},
    }

    for e in entries:
        p = e.get("prompt_tokens", 0)
        c = e.get("candidate_tokens", 0)
        t = e.get("total_tokens", p + c)
        cat = e.get("category", "general")
        model = e.get("model", "unknown")

        summary["prompt_tokens"] += p
        summary["candidate_tokens"] += c
        summary["total_tokens"] += t

        summary["categories"][cat] = summary["categories"].get(cat, 0) + t
        summary["models"][model] = summary["models"].get(model, 0) + t

    return summary


# ── Benchmark Runner Class ────────────────────────────────────────────────────
class BenchmarkRunner:

    def __init__(
        self,
        goal: str = "AI in HR",
        platforms: Optional[List[str]] = None,
        limit: int = 10,
        use_ai_classify: bool = True,
        use_ai_comment: bool = True,
        use_cache: bool = False,
    ):
        self.goal = goal
        self.platforms = platforms or ["youtube", "meetup", "web", "linkedin", "x", "tiktok"]
        self.limit = limit
        self.use_ai_classify = use_ai_classify
        self.use_ai_comment = use_ai_comment
        self.use_cache = use_cache
        self.reports_dir = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "data", "benchmark_reports")
        )
        os.makedirs(self.reports_dir, exist_ok=True)

    def run(self) -> Dict[str, Any]:
        """
        Thực thi quá trình benchmark crawler và đo lường token waste.
        """
        from services.ai_crawl_tool import (
            crawl_youtube_live,
            crawl_meetup,
            crawl_x_live,
            crawl_tiktok_live,
            crawl_linkedin,
            crawl_web,
            deduplicate_events,
            time_filter_events,
            filter_and_score_events,
            get_or_compile,
            build_fallback,
        )
        from ai.classify import classify_event
        from ai.comments import generate_comments

        start_time = time.time()
        timestamp_start_tokens = start_time

        print("=" * 80)
        print(f"⚡ ĐANG CHẠY BENCHMARK CRAWLER & TOKEN WASTE")
        print(f"  Goal       : '{self.goal}'")
        print(f"  Platforms  : {', '.join(self.platforms)}")
        print(f"  Limit      : {self.limit} / platform")
        print(f"  Classify   : {'Bật' if self.use_ai_classify else 'Tắt'}")
        print(f"  Comments   : {'Bật' if self.use_ai_comment else 'Tắt'}")
        print(f"  Cache      : {'Dùng' if self.use_cache else 'Bỏ qua (Fresh Crawl)'}")
        print("=" * 80)

        # Step 1: Goal Profile Compilation
        t0 = time.time()
        if self.use_ai_classify:
            profile = get_or_compile(self.goal, force_recompile=not self.use_cache)
        else:
            profile = None

        if profile:
            analysis = {
                "industries": profile.get("industries", []),
                "personas": profile.get("personas", []),
                "topics": profile.get("topics", []),
                "positive_keywords": profile.get("positive_keywords", []),
                "negative_keywords": profile.get("negative_keywords", []),
            }
            queries = profile.get("search_queries", [self.goal])
        else:
            analysis = build_fallback(self.goal)
            queries = [self.goal]

        compile_time = time.time() - t0

        platform_crawlers = {
            "youtube": crawl_youtube_live,
            "meetup": crawl_meetup,
            "x": crawl_x_live,
            "tiktok": crawl_tiktok_live,
            "linkedin": crawl_linkedin,
            "web": crawl_web,
        }

        try:
            from crawler.eventbrite import crawl_eventbrite
            if crawl_eventbrite:
                platform_crawlers["eventbrite"] = crawl_eventbrite
        except Exception:
            pass

        platform_results = {}
        all_raw_events = []
        all_dedup_events = []

        # Step 2: Per-Platform Benchmark
        for plat in self.platforms:
            crawler_fn = platform_crawlers.get(plat)
            if not crawler_fn:
                print(f"  ⚠️ Bỏ qua nền tảng không hỗ trợ: {plat}")
                continue

            print(f"  ▶ Crawling {plat}...")
            p_start = time.time()
            error_msg = None
            raw_items = []

            try:
                base_queries = queries[:5]
                try:
                    raw_items = crawler_fn(base_queries, self.limit)
                except TypeError:
                    raw_items = crawler_fn(base_queries, self.limit)
            except Exception as e:
                error_msg = str(e)
                print(f"    ❌ Lỗi crawler {plat}: {e}")

            p_latency = round(time.time() - p_start, 3)

            # Deduplication pass
            seen_tmp = set()
            dedup_items = deduplicate_events(raw_items, seen=seen_tmp)

            # Time filter pass
            time_filtered_items = time_filter_events(dedup_items)

            # Scoring pass
            scored_items = filter_and_score_events(time_filtered_items, analysis, goal=self.goal)

            high_count = sum(1 for item in scored_items if item.get("score", 0) >= 40)
            med_count = sum(1 for item in scored_items if 20 <= item.get("score", 0) < 40)
            low_count = sum(1 for item in scored_items if item.get("score", 0) < 20)
            avg_score = round(
                sum(item.get("score", 0) for item in scored_items) / max(1, len(scored_items)),
                1,
            )

            # Field completeness check
            completed_fields_sum = 0
            for it in raw_items:
                fields_ok = sum(1 for f in ["title", "url", "status", "channel_name"] if it.get(f))
                completed_fields_sum += (fields_ok / 4.0)
            completeness_rate = round((completed_fields_sum / max(1, len(raw_items))) * 100, 1)

            # Live precision check (Live or Upcoming vs static VODs)
            live_status_count = sum(1 for it in raw_items if it.get("status") in ("LIVE", "UPCOMING"))
            live_precision = round((live_status_count / max(1, len(raw_items))) * 100, 1)

            platform_results[plat] = {
                "latency_seconds": p_latency,
                "raw_count": len(raw_items),
                "dedup_count": len(dedup_items),
                "valid_time_count": len(time_filtered_items),
                "scored_count": len(scored_items),
                "avg_score": avg_score,
                "high_priority_count": high_count,
                "medium_priority_count": med_count,
                "low_priority_count": low_count,
                "live_precision_rate": live_precision,
                "field_completeness_rate": completeness_rate,
                "throughput_items_per_sec": round(len(raw_items) / max(0.001, p_latency), 2),
                "error": error_msg,
            }

            all_raw_events.extend(raw_items)
            all_dedup_events.extend(scored_items)

        # Step 3: AI Pipeline Classification & Comment Generation & Token Waste Calculation
        classified_events = []
        useful_lead_count = 0

        low_relevance_waste_tokens = 0
        duplicate_waste_tokens = 0
        time_filtered_waste_tokens = 0
        useful_tokens_count = 0

        for event in all_dedup_events:
            url = event.get("url", "")
            title = event.get("title", "")
            desc = event.get("description", "")
            score = event.get("score", 0)

            is_in_db = bool(get_event_by_url(url)) if url else False

            t_before = get_token_log_entries(timestamp_start_tokens)
            tokens_before_call = sum(e.get("total_tokens", 0) for e in t_before)

            # Classify
            if self.use_ai_classify:
                try:
                    c_res = classify_event(title, desc, goal=self.goal)
                    event.update({
                        "industry": c_res.get("industry", ""),
                        "buyer_persona": c_res.get("buyer_persona", ""),
                        "score": c_res.get("score", score),
                        "priority": c_res.get("priority", "Low"),
                        "interaction_tip": c_res.get("interaction_tip", ""),
                        "suggested_comment": c_res.get("suggested_comment", ""),
                    })
                except Exception as e:
                    print(f"  ⚠️ Classify error for '{title[:30]}': {e}")

            # Comment Generation
            if self.use_ai_comment and event.get("score", 0) >= 20:
                try:
                    comments = generate_comments(title, desc, goal=self.goal)
                    if comments:
                        event["suggested_comments"] = comments
                except Exception as e:
                    print(f"  ⚠️ Comment error for '{title[:30]}': {e}")

            t_after = get_token_log_entries(timestamp_start_tokens)
            tokens_after_call = sum(e.get("total_tokens", 0) for e in t_after)
            event_tokens = tokens_after_call - tokens_before_call

            if is_in_db:
                duplicate_waste_tokens += event_tokens
            elif score < 20:
                low_relevance_waste_tokens += event_tokens
            else:
                useful_tokens_count += event_tokens
                useful_lead_count += 1

            classified_events.append(event)

        total_duration = round(time.time() - start_time, 2)

        # Step 4: 4-Pillar Agent Evaluation Metrics
        token_entries = get_token_log_entries(timestamp_start_tokens)
        token_summary = summarize_tokens(token_entries)
        total_tokens_consumed = token_summary["total_tokens"]

        total_wasted_tokens = low_relevance_waste_tokens + duplicate_waste_tokens + time_filtered_waste_tokens
        useful_tokens_calculated = total_tokens_consumed - total_wasted_tokens
        if useful_tokens_calculated < 0:
            useful_tokens_calculated = 0

        waste_percentage = round((total_wasted_tokens / max(1, total_tokens_consumed)) * 100, 1)
        efficiency_percentage = round(100.0 - waste_percentage, 1)
        tokens_per_lead = round(total_tokens_consumed / max(1, useful_lead_count), 1)

        total_raw = sum(v["raw_count"] for v in platform_results.values())
        total_dedup = sum(v["dedup_count"] for v in platform_results.values())
        total_scored = sum(v["scored_count"] for v in platform_results.values())
        total_high = sum(v["high_priority_count"] for v in platform_results.values())
        total_med = sum(v["medium_priority_count"] for v in platform_results.values())

        # Pillar 1: Scraper Performance
        total_live_items = sum(1 for it in all_raw_events if it.get("status") in ("LIVE", "UPCOMING"))
        live_precision_overall = round((total_live_items / max(1, total_raw)) * 100, 1)
        
        all_field_checks = 0
        for it in all_raw_events:
            ok_cnt = sum(1 for f in ["title", "url", "status", "channel_name"] if it.get(f))
            all_field_checks += (ok_cnt / 4.0)
        overall_completeness = round((all_field_checks / max(1, total_raw)) * 100, 1)

        # Pillar 2: Relevance & AI Precision
        top_5_events = all_dedup_events[:5]
        top_10_events = all_dedup_events[:10]
        p_at_5 = round((sum(1 for it in top_5_events if it.get("score", 0) >= 40) / max(1, len(top_5_events))) * 100, 1) if top_5_events else 0.0
        p_at_10 = round((sum(1 for it in top_10_events if it.get("score", 0) >= 40) / max(1, len(top_10_events))) * 100, 1) if top_10_events else 0.0
        
        spam_items_count = sum(1 for it in all_dedup_events if it.get("score", 0) < 20)
        spam_leakage_rate = round((spam_items_count / max(1, len(all_dedup_events))) * 100, 1)

        # Mean Reciprocal Rank (MRR)
        first_relevant_rank = None
        for idx, it in enumerate(all_dedup_events):
            if it.get("score", 0) >= 40:
                first_relevant_rank = idx + 1
                break
        mrr = round(1.0 / first_relevant_rank, 3) if first_relevant_rank else 0.0

        # Pillar 4: Lead Actionability & Third-Party LLM Judge
        high_priority_ratio = round((total_high / max(1, total_scored)) * 100, 1)
        avg_lead_score = round(sum(it.get("score", 0) for it in all_dedup_events) / max(1, len(all_dedup_events)), 1)

        # Evaluate with Third-Party LLM-as-a-Judge
        from ai.judge_evaluator import evaluate_with_llm_judge
        from services.golden_evaluator import compute_ndcg_at_k

        judge_scores = []
        judge_evaluated_items = []
        relevance_grades = []

        for rank, ev in enumerate(all_dedup_events[:10], 1):
            title_txt = ev.get("title", "")
            desc_txt = ev.get("description", "")
            ch_txt = ev.get("channel_name", "")
            st_txt = ev.get("status", "LIVE")
            vw_txt = ev.get("concurrent_viewers", "")

            j_res = evaluate_with_llm_judge(
                title=title_txt,
                description=desc_txt,
                channel_name=ch_txt,
                goal=self.goal,
                status=st_txt,
                viewers=vw_txt,
            )
            j_sc = j_res.get("judge_score", 0.0)
            judge_scores.append(j_sc)

            rel_g = 3.0 if j_sc >= 80 else (2.0 if j_sc >= 50 else (1.0 if j_sc >= 30 else 0.0))
            relevance_grades.append(rel_g)

            judge_evaluated_items.append({
                "rank": rank,
                "title": title_txt,
                "url": ev.get("url", ""),
                "channel_name": ch_txt,
                "status": st_txt,
                "viewers": vw_txt,
                "judge_score": j_sc,
                "is_relevant": j_res.get("is_relevant", j_sc >= 50),
                "is_spam": j_res.get("is_spam", False),
                "critique": j_res.get("critique", ""),
                "judge_model": j_res.get("judge_model", "third-party-judge"),
            })

        ndcg_5_judge = compute_ndcg_at_k(relevance_grades, k=5)
        avg_g_eval = round(sum(judge_scores) / max(1, len(judge_scores)), 1)

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "goal": self.goal,
            "duration_seconds": total_duration,
            "compile_time_seconds": round(compile_time, 3),
            "platforms": self.platforms,
            "overall_metrics": {
                "total_raw_events": total_raw,
                "total_dedup_events": total_dedup,
                "total_relevance_passed": total_scored,
                "total_high_priority": total_high,
                "total_medium_priority": total_med,
                "useful_leads_saved": useful_lead_count,
                "overall_dedup_rate": round((1 - total_dedup / max(1, total_raw)) * 100, 1),
            },
            "third_party_judge": {
                "g_eval_score": avg_g_eval,
                "ndcg_at_5": ndcg_5_judge,
                "items_evaluated": len(judge_evaluated_items),
                "evaluated_items": judge_evaluated_items,
            },
            "evaluation_metrics": {
                "pillar_1_scraper_performance": {
                    "live_precision_rate": live_precision_overall,
                    "field_completeness_rate": overall_completeness,
                    "throughput_items_per_sec": round(total_raw / max(0.001, total_duration), 2),
                    "avg_latency_per_item_sec": round(total_duration / max(1, total_raw), 2),
                },
                "pillar_2_relevance_quality": {
                    "precision_at_5": p_at_5,
                    "precision_at_10": p_at_10,
                    "spam_leakage_rate": spam_leakage_rate,
                    "mean_reciprocal_rank": mrr,
                    "status_accuracy_rate": 100.0 if total_live_items == total_raw else round((total_live_items / max(1, total_raw)) * 100, 1),
                },
                "pillar_3_token_economy": {
                    "total_tokens_consumed": total_tokens_consumed,
                    "useful_tokens": useful_tokens_calculated,
                    "wasted_tokens": total_wasted_tokens,
                    "token_efficiency_percentage": efficiency_percentage,
                    "token_waste_percentage": waste_percentage,
                    "tokens_per_qualified_lead": tokens_per_lead,
                    "cost_estimate_usd": round((total_tokens_consumed / 1_000_000) * 0.15, 6),
                },
                "pillar_4_lead_actionability": {
                    "high_priority_ratio": high_priority_ratio,
                    "avg_lead_score": avg_lead_score,
                    "useful_lead_count": useful_lead_count,
                },
            },
            "platform_breakdown": platform_results,
            "token_metrics": {
                "total_prompt_tokens": token_summary["prompt_tokens"],
                "total_candidate_tokens": token_summary["candidate_tokens"],
                "total_tokens_consumed": total_tokens_consumed,
                "useful_tokens": useful_tokens_calculated,
                "wasted_tokens": total_wasted_tokens,
                "waste_breakdown": {
                    "low_relevance_waste": low_relevance_waste_tokens,
                    "duplicate_waste": duplicate_waste_tokens,
                    "expired_time_waste": time_filtered_waste_tokens,
                },
                "token_waste_percentage": waste_percentage,
                "token_efficiency_percentage": efficiency_percentage,
                "tokens_per_qualified_lead": tokens_per_lead,
                "category_breakdown": token_summary["categories"],
                "model_breakdown": token_summary["models"],
            },
        }

        # Save Report JSON
        report_filename = f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path = os.path.join(self.reports_dir, report_filename)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print("=" * 80)
        print(f"✅ BENCHMARK HOÀN TẤT TRONG {total_duration}s")
        print(f"  → G-Eval Judge Score: {avg_g_eval}/100 | NDCG@5: {ndcg_5_judge}")
        print(f"  → Live Precision: {live_precision_overall}% | Completeness: {overall_completeness}%")
        print(f"  → Precision@5: {p_at_5}% | MRR: {mrr} | Spam Leakage: {spam_leakage_rate}%")
        print(f"  → Token tiêu thụ: {total_tokens_consumed:,} | Hiệu quả: {efficiency_percentage}%")
        print(f"  → File báo cáo: {report_path}")
        print("=" * 80)

        return report


def list_benchmark_reports(limit: int = 10) -> List[Dict[str, Any]]:
    """Liệt kê các báo cáo benchmark đã chạy trước đây."""
    reports_dir = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "data", "benchmark_reports")
    )
    if not os.path.exists(reports_dir):
        return []

    reports = []
    for fname in os.listdir(reports_dir):
        if fname.endswith(".json"):
            fpath = os.path.join(reports_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    data["_filename"] = fname
                    data["_filepath"] = fpath
                    reports.append(data)
            except Exception:
                pass

    return sorted(reports, key=lambda x: x.get("timestamp", ""), reverse=True)[:limit]
