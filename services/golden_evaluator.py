"""
services/golden_evaluator.py — Golden Dataset Benchmark & Third-Party Judge Engine
===================================================================================
Runs the AI Discovery Agent across the Golden Benchmark Dataset (BEIR/GAIA style),
evaluating retrieval quality via standard Information Retrieval metrics (NDCG@K, MRR, MAP)
and an independent Third-Party LLM-as-a-Judge (G-Eval Rubric).
"""

import os
import json
import time
import math
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from ai.judge_evaluator import evaluate_with_llm_judge
from services.ai_crawl_tool import crawl_livestreams_with_ai


def _compute_dcg(relevances: List[float], k: int) -> float:
    """Computes Discounted Cumulative Gain at rank K."""
    dcg = 0.0
    for i, rel in enumerate(relevances[:k]):
        gain = (2.0 ** rel) - 1.0
        discount = math.log2(i + 2)
        dcg += gain / discount
    return dcg


def compute_ndcg_at_k(relevances: List[float], k: int = 5) -> float:
    """
    Computes Normalized Discounted Cumulative Gain at rank K (0.0 to 1.0).
    Standard metric used in Google Search, Bing, and MS MARCO benchmarks.
    """
    if not relevances:
        return 0.0
    actual_dcg = _compute_dcg(relevances, k)
    ideal_relevances = sorted(relevances, reverse=True)
    ideal_dcg = _compute_dcg(ideal_relevances, k)
    if ideal_dcg == 0.0:
        return 1.0 if actual_dcg == 0.0 else 0.0
    return round(min(1.0, actual_dcg / ideal_dcg), 3)


def compute_average_precision(is_relevant_list: List[bool]) -> float:
    """Computes Average Precision (AP) for a single query."""
    if not is_relevant_list or not any(is_relevant_list):
        return 0.0
    running_relevant = 0
    precision_sum = 0.0
    for i, is_rel in enumerate(is_relevant_list):
        if is_rel:
            running_relevant += 1
            precision_sum += running_relevant / (i + 1)
    return round(precision_sum / max(1, sum(1 for r in is_relevant_list if r)), 3)


class GoldenDatasetEvaluator:
    """
    Automated Benchmark Runner executing tests against data/golden_dataset.json.
    """

    def __init__(
        self,
        dataset_path: Optional[str] = None,
        max_test_cases: int = 5,
        items_per_query: int = 5,
        use_llm_judge: bool = True,
    ):
        if dataset_path is None:
            dataset_path = os.path.normpath(
                os.path.join(os.path.dirname(__file__), "..", "data", "golden_dataset.json")
            )
        self.dataset_path = dataset_path
        self.max_test_cases = max_test_cases
        self.items_per_query = items_per_query
        self.use_llm_judge = use_llm_judge
        self.reports_dir = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "data", "benchmark_reports")
        )
        os.makedirs(self.reports_dir, exist_ok=True)

    def load_dataset(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.dataset_path):
            return []
        try:
            with open(self.dataset_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Golden Evaluator] Error loading dataset: {e}")
            return []

    def run_evaluation(self) -> Dict[str, Any]:
        dataset = self.load_dataset()
        if not dataset:
            raise RuntimeError(f"Golden dataset not found at {self.dataset_path}")

        test_cases = dataset[:self.max_test_cases]
        print("=" * 85)
        print(f"🏛️ ĐANG CHẠY ĐÁNH GIÁ AGENT VỚI HỘI ĐỒNG GIÁM KHẢO ĐỘC LẬP (GOLDEN EVALUATOR)")
        print(f"  • Số lượng bài test  : {len(test_cases)} test cases")
        print(f"  • Số kết quả / query : {self.items_per_query} items")
        print(f"  • Giám khảo bên thứ 3: {'BẬT (LLM-as-a-Judge)' if self.use_llm_judge else 'TẮT (Rule-based)'}")
        print("=" * 85)

        start_time = time.time()
        test_results = []
        all_ndcg_5 = []
        all_ndcg_10 = []
        all_mrr = []
        all_ap = []
        all_judge_scores = []
        total_spam_detected = 0
        total_items_evaluated = 0

        for idx, test_case in enumerate(test_cases, 1):
            goal = test_case.get("goal", "")
            test_id = test_case.get("id", f"TEST_{idx:03d}")
            category = test_case.get("category", "General")
            print(f"\n▶ [{idx}/{len(test_cases)}] Đang kiểm thử: '{goal}' ({category})...")

            t_query_start = time.time()
            agent_result = crawl_livestreams_with_ai(
                goal,
                limit=self.items_per_query,
                platforms=["youtube"],
                mode="ai_then_fallback",
                per_platform_timeout=25,
                use_youtube_api=False,
                use_headless=True,
            )
            events = agent_result.get("events", [])
            query_latency = round(time.time() - t_query_start, 2)
            print(f"  → Agent tìm được {len(events)} livestream trong {query_latency}s")

            relevance_scale_list = []
            is_relevant_bool_list = []
            evaluated_items = []
            first_relevant_rank = None

            for rank, ev in enumerate(events, 1):
                title = ev.get("title", "")
                desc = ev.get("description", "")
                channel = ev.get("channel_name", "")
                status = ev.get("status", "LIVE")
                viewers = ev.get("concurrent_viewers", "")

                if self.use_llm_judge:
                    judge_out = evaluate_with_llm_judge(
                        title=title,
                        description=desc,
                        channel_name=channel,
                        goal=goal,
                        status=status,
                        viewers=viewers,
                    )
                else:
                    match_score = ev.get("score", 0)
                    judge_out = {
                        "judge_score": float(match_score),
                        "is_relevant": match_score >= 40,
                        "is_spam": match_score < 20,
                        "critique": "Heuristic match score.",
                        "judge_model": "rule-based",
                    }

                j_score = judge_out.get("judge_score", 0.0)
                is_rel = judge_out.get("is_relevant", j_score >= 50.0)
                is_sp = judge_out.get("is_spam", False)

                all_judge_scores.append(j_score)
                total_items_evaluated += 1
                if is_sp:
                    total_spam_detected += 1

                rel_grade = 3.0 if j_score >= 80 else (2.0 if j_score >= 50 else (1.0 if j_score >= 30 else 0.0))
                relevance_scale_list.append(rel_grade)
                is_relevant_bool_list.append(is_rel)

                if is_rel and first_relevant_rank is None:
                    first_relevant_rank = rank

                evaluated_items.append({
                    "rank": rank,
                    "title": title,
                    "url": ev.get("url", ""),
                    "channel": channel,
                    "judge_score": j_score,
                    "is_relevant": is_rel,
                    "is_spam": is_sp,
                    "critique": judge_out.get("critique", ""),
                })

            ndcg_5 = compute_ndcg_at_k(relevance_scale_list, k=5)
            ndcg_10 = compute_ndcg_at_k(relevance_scale_list, k=10)
            mrr_query = round(1.0 / first_relevant_rank, 3) if first_relevant_rank else 0.0
            ap_query = compute_average_precision(is_relevant_bool_list)

            all_ndcg_5.append(ndcg_5)
            all_ndcg_10.append(ndcg_10)
            all_mrr.append(mrr_query)
            all_ap.append(ap_query)

            print(f"  → NDCG@5: {ndcg_5} | MRR: {mrr_query} | Avg Judge Score: {round(sum(relevance_scale_list)/max(1, len(relevance_scale_list))*33.3, 1)}/100")

            test_results.append({
                "test_id": test_id,
                "goal": goal,
                "category": category,
                "latency_seconds": query_latency,
                "items_retrieved": len(events),
                "ndcg_at_5": ndcg_5,
                "ndcg_at_10": ndcg_10,
                "mrr": mrr_query,
                "average_precision": ap_query,
                "items": evaluated_items,
            })

        total_eval_time = round(time.time() - start_time, 2)
        mean_ndcg_5 = round(sum(all_ndcg_5) / max(1, len(all_ndcg_5)), 3)
        mean_ndcg_10 = round(sum(all_ndcg_10) / max(1, len(all_ndcg_10)), 3)
        mean_mrr = round(sum(all_mrr) / max(1, len(all_mrr)), 3)
        map_score = round(sum(all_ap) / max(1, len(all_ap)), 3)
        avg_g_eval_score = round(sum(all_judge_scores) / max(1, len(all_judge_scores)), 1)
        spam_leakage_pct = round((total_spam_detected / max(1, total_items_evaluated)) * 100, 1)

        summary_report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "evaluation_type": "Golden Dataset Benchmark (LLM-as-a-Judge)",
            "benchmark_dataset": "data/golden_dataset.json",
            "total_test_cases": len(test_cases),
            "total_duration_seconds": total_eval_time,
            "overall_benchmarks": {
                "g_eval_judge_score": avg_g_eval_score,
                "ndcg_at_5": mean_ndcg_5,
                "ndcg_at_10": mean_ndcg_10,
                "mrr_mean_reciprocal_rank": mean_mrr,
                "map_mean_average_precision": map_score,
                "spam_leakage_rate": spam_leakage_pct,
                "total_items_tested": total_items_evaluated,
            },
            "test_case_breakdown": test_results,
        }

        report_filename = f"golden_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path = os.path.join(self.reports_dir, report_filename)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(summary_report, f, ensure_ascii=False, indent=2)

        print("\n" + "=" * 85)
        print(f"🏆 KẾT QUẢ ĐÁNH GIÁ TỔNG QUAN VỚI BÊN THỨ 3 (HỘI ĐỒNG GIÁM KHẢO)")
        print("=" * 85)
        print(f"  • G-Eval Score (Điểm Giám Khảo Độc Lập) : {avg_g_eval_score} / 100")
        print(f"  • NDCG@5 (Xếp hạng chuẩn Top 5)         : {mean_ndcg_5} / 1.000")
        print(f"  • NDCG@10 (Xếp hạng chuẩn Top 10)       : {mean_ndcg_10} / 1.000")
        print(f"  • MRR (Mean Reciprocal Rank)            : {mean_mrr}")
        print(f"  • MAP (Mean Average Precision)          : {map_score}")
        print(f"  • Tỷ lệ lọt video rác (Spam Leakage)    : {spam_leakage_pct}%")
        print(f"  • Thời gian hoàn thành                  : {total_eval_time}s")
        print(f"  • File báo cáo chi tiết                 : {report_path}")
        print("=" * 85 + "\n")

        return summary_report
