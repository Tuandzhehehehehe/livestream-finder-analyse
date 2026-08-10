#!/usr/bin/env python
"""
benchmark.py — CLI Tool to Benchmark Crawler Performance & Token Waste
========================================================================

Usage examples:
  # Benchmark all default platforms with a custom goal:
  python benchmark.py --goal "SaaS Marketing"

  # Benchmark specific platforms:
  python benchmark.py --platforms youtube meetup web --limit 5

  # Benchmark raw crawler performance only (saves AI tokens):
  python benchmark.py --no-ai

  # List past benchmark reports:
  python benchmark.py --list-reports
"""

import sys
import os
import argparse
import json

# Ensure project root in pythonpath
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.benchmarker import BenchmarkRunner, list_benchmark_reports


def print_report_summary(report: dict):
    print("\n" + "=" * 85)
    print("🎯 BÁO CÁO ĐÁNH GIÁ AGENT LIVESTREAM & TOKEN WASTE (4-PILLAR EVALUATOR)")
    print("=" * 85)

    g = report.get("goal", "")
    dur = report.get("duration_seconds", 0)
    ts = report.get("timestamp", "")
    print(f"  • Mục tiêu tìm kiếm (Goal)   : '{g}'")
    print(f"  • Thời gian chạy (Execution) : {dur}s | Compile Goal Profile: {report.get('compile_time_seconds', 0)}s")
    print(f"  • Thời điểm ghi nhận (Time)  : {ts[:19].replace('T', ' ')}")
    print("-" * 85)

    em = report.get("evaluation_metrics", {})
    p1 = em.get("pillar_1_scraper_performance", {})
    p2 = em.get("pillar_2_relevance_quality", {})
    p3 = em.get("pillar_3_token_economy", {})
    p4 = em.get("pillar_4_lead_actionability", {})

    print("1️⃣ TRỤ CỘT 1: HIỆU NĂNG THU THẬP & PLAYWRIGHT SCRAPER (SCRAPER PERFORMANCE)")
    print(f"   • Live Precision Rate (Tỷ lệ Live chuẩn) : {p1.get('live_precision_rate', 0)}% (Không bị lẫn video tĩnh)")
    print(f"   • Field Completeness (Đầy đủ dữ liệu)   : {p1.get('field_completeness_rate', 0)}% (Title, Channel, Status, Time)")
    print(f"   • Tốc độ bóc tách (Throughput)          : {p1.get('throughput_items_per_sec', 0)} items/s")
    print(f"   • Độ trễ trung bình / item (Latency)    : {p1.get('avg_latency_per_item_sec', 0)}s / item")
    print("-" * 85)

    print("2️⃣ TRỤ CỘT 2: CHẤT LƯỢNG PHÙ HỢP & PHÂN LOẠI AI (RELEVANCE & AI QUALITY)")
    print(f"   • Precision@5 (Chính xác trong Top 5)   : {p2.get('precision_at_5', 0)}%")
    print(f"   • Precision@10 (Chính xác trong Top 10) : {p2.get('precision_at_10', 0)}%")
    print(f"   • Spam Leakage Rate (Rác lọt qua lọc)   : {p2.get('spam_leakage_rate', 0)}% (Chặn sạch video không liên quan)")
    print(f"   • Mean Reciprocal Rank (MRR)            : {p2.get('mean_reciprocal_rank', 0)} (Điểm xếp hạng kết quả tốt nhất)")
    print(f"   • Status Classification Accuracy        : {p2.get('status_accuracy_rate', 0)}% (Đúng trạng thái LIVE/UPCOMING)")
    print("-" * 85)

    print("3️⃣ TRỤ CỘT 3: HIỆU QUẢ KINH TẾ & TIẾT KIỆM TOKEN AI (TOKEN ECONOMY & WASTE)")
    print(f"   • Tổng Token Tiêu Thụ                   : {p3.get('total_tokens_consumed', 0):,} tokens (~ ${p3.get('cost_estimate_usd', 0):.6f})")
    print(f"   • Token Có Ích (Useful Tokens)          : {p3.get('useful_tokens', 0):,} ({p3.get('token_efficiency_percentage', 0)}% hiệu quả)")
    print(f"   • Token Lãng Phí (Wasted Tokens)        : {p3.get('wasted_tokens', 0):,} ({p3.get('token_waste_percentage', 0)}% lãng phí)")
    print(f"   • Chi Phí Token / Lead Đạt Chuẩn        : {p3.get('tokens_per_qualified_lead', 0):,} tokens / Lead")
    
    wb = report.get("token_metrics", {}).get("waste_breakdown", {})
    if wb:
        print(f"     └─ Phân tích lãng phí: {wb.get('low_relevance_waste', 0):,} tokens (Score < 20) | {wb.get('duplicate_waste', 0):,} tokens (Trùng DB)")
    print("-" * 85)

    print("4️⃣ TRỤ CỘT 4: GIÁ TRỊ CHUYỂN ĐỔI & TÍNH HÀNH ĐỘNG (LEAD ACTIONABILITY)")
    print(f"   • High-Priority Leads (Score >= 80)     : {p4.get('high_priority_ratio', 0)}% ({report.get('overall_metrics', {}).get('total_high_priority', 0)} leads)")
    print(f"   • Điểm Tiềm Năng Trung Bình (Avg Score) : {p4.get('avg_lead_score', 0)} / 100")
    print(f"   • Số Lead Đạt Chuẩn Lưu DB               : {p4.get('useful_lead_count', 0)} leads")
    print("=" * 85 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="AI Livestream Finder — Crawler Performance & Token Waste Benchmarking Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--goal",
        type=str,
        default="AI in HR",
        help="Goal query to benchmark (default: 'AI in HR')",
    )
    parser.add_argument(
        "--platforms",
        nargs="*",
        default=None,
        help="Platforms to test: youtube meetup linkedin x tiktok web eventbrite (default: youtube meetup web linkedin x tiktok)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Max items to fetch per platform (default: 10)",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Disable AI classification and comment generation (benchmark raw crawler yield/latency only)",
    )
    parser.add_argument(
        "--no-comment",
        action="store_true",
        help="Disable comment generation stage",
    )
    parser.add_argument(
        "--use-cache",
        action="store_true",
        help="Enable cache (default is false for benchmark accuracy)",
    )
    parser.add_argument(
        "--run-golden-eval",
        action="store_true",
        help="Run comprehensive benchmark against the Golden Dataset with Third-Party LLM Judge",
    )
    parser.add_argument(
        "--golden-cases",
        type=int,
        default=3,
        help="Number of test cases to run from golden_dataset.json (default: 3)",
    )
    parser.add_argument(
        "--no-judge",
        action="store_true",
        help="Disable LLM-as-a-Judge for Golden Dataset (use rule-based scoring)",
    )
    parser.add_argument(
        "--hf-dataset",
        type=str,
        default=None,
        help="Run benchmark against universal Hugging Face dataset (e.g. 'BeIR/fiqa', 'BeIR/scifact', 'microsoft/ms_marco')",
    )
    parser.add_argument(
        "--hf-queries",
        type=int,
        default=3,
        help="Number of queries to test from Hugging Face dataset (default: 3)",
    )
    parser.add_argument(
        "--list-reports",
        action="store_true",
        help="List previously generated benchmark reports",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw report output in JSON format",
    )

    args = parser.parse_args()

    # ── Chạy Universal Hugging Face Benchmark ──────────────────────────────
    if args.hf_dataset:
        from services.huggingface_evaluator import HuggingFaceBenchmarkEvaluator
        hf_eval = HuggingFaceBenchmarkEvaluator(
            dataset_name=args.hf_dataset,
            max_queries=args.hf_queries,
        )
        report = hf_eval.evaluate_agent_against_hf_benchmark()
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    # ── Chạy Golden Benchmark với Hội đồng giám khảo bên thứ 3 ───────────────
    if args.run_golden_eval:
        from services.golden_evaluator import GoldenDatasetEvaluator
        evaluator = GoldenDatasetEvaluator(
            max_test_cases=args.golden_cases,
            items_per_query=args.limit,
            use_llm_judge=not args.no_judge,
        )
        report = evaluator.run_evaluation()
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    if args.list_reports:
        reports = list_benchmark_reports(limit=10)
        if not reports:
            print("Chưa có báo cáo benchmark nào được tạo.")
            return

        print("\n" + "=" * 80)
        print("📜 DANH SÁCH BÁO CÁO BENCHMARK ĐÃ LƯU")
        print("=" * 80)
        for r in reports:
            fname = r.get("_filename", "")
            ts = r.get("timestamp", "")
            g = r.get("goal", "")
            dur = r.get("duration_seconds", 0)
            tm = r.get("token_metrics", {})
            tot = tm.get("total_tokens_consumed", 0)
            waste = tm.get("token_waste_percentage", 0)
            print(f" • {fname:<30} | {ts[:19]} | Goal: '{g}' | {dur}s | {tot:,} tokens | {waste}% waste")
        print("=" * 80 + "\n")
        return

    runner = BenchmarkRunner(
        goal=args.goal,
        platforms=args.platforms,
        limit=args.limit,
        use_ai_classify=not args.no_ai,
        use_ai_comment=(not args.no_ai and not args.no_comment),
        use_cache=args.use_cache,
    )

    report = runner.run()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report_summary(report)


if __name__ == "__main__":
    main()
