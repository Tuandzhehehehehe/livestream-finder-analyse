#!/usr/bin/env python
"""
auto_crawl.py -- Automated crawler with scheduler
==================================================

Usage:
  # Run once immediately:
  py auto_crawl.py --once

  # Run on schedule every 2 hours (default):
  py auto_crawl.py

  # Run every 4 hours, only crawl LinkedIn and Meetup:
  py auto_crawl.py --interval 4 --platforms linkedin meetup

  # Disable auto-classify and comments (crawl only, saves tokens):
  py auto_crawl.py --no-classify --no-comment

  # Help:
  py auto_crawl.py --help
"""

import argparse
import sys
import os

# Ensure imports from project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    parser = argparse.ArgumentParser(
        description="AI Livestream Finder -- Auto Crawler",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (do not repeat on schedule)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        metavar="HOURS",
        help="Hours between each crawl run. Default: 2",
    )
    parser.add_argument(
        "--platforms",
        nargs="*",
        default=None,
        metavar="PLATFORM",
        help="Platforms to crawl: youtube meetup linkedin web ... (default: all)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        metavar="N",
        help="Max events per goal per run. Default: 20",
    )
    parser.add_argument(
        "--no-classify",
        action="store_true",
        help="Disable AI classify (saves tokens)",
    )
    parser.add_argument(
        "--no-comment",
        action="store_true",
        help="Disable AI comment generation (saves tokens)",
    )

    args = parser.parse_args()

    auto_classify = not args.no_classify
    auto_comment = not args.no_comment

    print("=" * 60)
    print("🤖 AI Livestream Finder — Auto Crawler")
    print("=" * 60)
    print(f"  Platforms : {args.platforms or 'tất cả'}")
    print(f"  Limit     : {args.limit} event / goal")
    print(f"  Classify  : {'✅' if auto_classify else '❌ (tắt)'}")
    print(f"  Comment   : {'✅' if auto_comment else '❌ (tắt)'}")
    if args.once:
        print("  Mode      : Chạy 1 lần")
    else:
        print(f"  Mode      : Lập lịch mỗi {args.interval} giờ")
    print("=" * 60)
    print()

    from services.auto_runner import run_once, start_scheduler

    if args.once:
        summary = run_once(
            platforms=args.platforms,
            limit=args.limit,
            auto_classify=auto_classify,
            auto_comment=auto_comment,
        )
        print()
        print("📊 Kết quả:")
        print(f"  ✔ Event mới lưu vào DB : {summary['total_new']}")
        print(f"  ⏭ Bỏ qua (đã có)      : {summary['total_skipped']}")
        print(f"  📋 Profiles đã chạy   : {summary['profiles_run']}")
        if summary["errors"]:
            print(f"  ❌ Lỗi                 : {len(summary['errors'])}")
            for err in summary["errors"]:
                print(f"     - {err}")
    else:
        start_scheduler(
            interval_hours=args.interval,
            platforms=args.platforms,
            limit=args.limit,
            auto_classify=auto_classify,
            auto_comment=auto_comment,
        )


if __name__ == "__main__":
    main()
