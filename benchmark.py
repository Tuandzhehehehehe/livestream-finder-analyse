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
    print("\n" + "=" * 80)
    print("📊 BÁO CÁO BENCHMARK KẾT QUẢ CRAWLER VÀ TOKEN WASTE")
    print("=" * 80)

    g = report.get("goal", "")
    dur = report.get("duration_seconds", 0)
    ts = report.get("timestamp", "")
    print(f"🎯 Mục tiêu (Goal)      : {g}")
    print(f"🕒 Thời gian thực thi    : {dur}s ({ts})")
    print(f"⚡ Thời gian compile     : {report.get('compile_time_seconds', 0)}s")
    print("-" * 80)

    om = report.get("overall_metrics", {})
    print("📈 TỔNG QUAN HIỆU SUẤT CRAWLER:")
    print(f"  • Tổng sự kiện tìm thấy (Raw)       : {om.get('total_raw_events', 0)}")
    print(f"  • Sự kiện sau loại trùng (Dedup)    : {om.get('total_dedup_events', 0)} ({om.get('overall_dedup_rate', 0)}% trùng lặp)")
    print(f"  • Sự kiện đạt ngưỡng phù hợp (Score): {om.get('total_relevance_passed', 0)}")
    print(f"  • Sự kiện ưu tiên cao (High)        : {om.get('total_high_priority', 0)}")
    print(f"  • Leads chất lượng được lưu DB       : {om.get('useful_leads_saved', 0)}")
    print("-" * 80)

    pb = report.get("platform_breakdown", {})
    print("🌐 CHI TIẾT THEO TỪNG NỀN TẢNG (PLATFORM BREAKDOWN):")
    print(f"{'Nền tảng':<12} | {'Thời gian (s)':<13} | {'Raw':<6} | {'Dedup':<6} | {'Scored':<7} | {'Avg Score':<10} | {'Throughput':<12}")
    print("-" * 80)
    for plat, pdata in pb.items():
        err = pdata.get("error")
        if err:
            print(f"{plat:<12} | {'LỖI: ' + err[:50]}")
        else:
            print(
                f"{plat:<12} | "
                f"{pdata.get('latency_seconds', 0):<13.2f} | "
                f"{pdata.get('raw_count', 0):<6} | "
                f"{pdata.get('dedup_count', 0):<6} | "
                f"{pdata.get('scored_count', 0):<7} | "
                f"{pdata.get('avg_score', 0):<10} | "
                f"{pdata.get('throughput_items_per_sec', 0):<12.1f} sps"
            )
    print("-" * 80)

    tm = report.get("token_metrics", {})
    print("💡 ĐO LƯỜNG SỬ DỤNG VÀ LÃNG PHÍ TOKEN AI (TOKEN WASTE METRICS):")
    print(f"  • Prompt Tokens                        : {tm.get('total_prompt_tokens', 0):,}")
    print(f"  • Candidate Tokens                     : {tm.get('total_candidate_tokens', 0):,}")
    print(f"  • Tổng Token Tiêu Thụ                   : {tm.get('total_tokens_consumed', 0):,}")
    print(f"  • Token Có Ích (Useful Tokens)          : {tm.get('useful_tokens', 0):,}")
    print(f"  • Token Lãng Phí (Wasted Tokens)        : {tm.get('wasted_tokens', 0):,} ({tm.get('token_waste_percentage', 0)}%)")
    print(f"  • Hiệu Suất Sử Dụng Token (Efficiency)  : {tm.get('token_efficiency_percentage', 0)}%")
    print(f"  • Chi Phí Token / Lead Chất Lượng      : {tm.get('tokens_per_qualified_lead', 0):,} tokens")

    wb = tm.get("waste_breakdown", {})
    if wb:
        print("\n  ⚠️ Phân tích nguyên nhân lãng phí token:")
        print(f"    - Do sự kiện không phù hợp (Score < 20) : {wb.get('low_relevance_waste', 0):,} tokens")
        print(f"    - Do sự kiện bị trùng lặp trong DB/Excel: {wb.get('duplicate_waste', 0):,} tokens")
        print(f"    - Do sự kiện đã hết hạn/quá cũ         : {wb.get('expired_time_waste', 0):,} tokens")

    cb = tm.get("category_breakdown", {})
    if cb:
        print("\n  📌 Tiêu thụ token theo từng công đoạn:")
        for cat, cnt in cb.items():
            print(f"    - {cat:<18}: {cnt:,} tokens")
    print("=" * 80 + "\n")


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
