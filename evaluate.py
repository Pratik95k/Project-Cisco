"""
NetSage AI - Evaluation Layer
Compares each AI diagnosis (results.json) against the ground truth
(cases.json) and computes accuracy stats, overall and per category.

Since 'root_cause' is free text, exact string matching won't work well.
Instead we use a keyword-overlap similarity score between the AI's
root_cause and the ground truth root_cause, plus a manual-friendly
match flag the human reviewer can override later.
"""

import json
import re
from collections import defaultdict


def normalize(text: str) -> set:
    """Lowercase, strip punctuation, split into a set of significant words."""
    if not text:
        return set()
    words = re.findall(r"[a-z0-9]+", text.lower())
    stopwords = {
        "the", "a", "an", "is", "are", "was", "were", "to", "for", "of", "in",
        "on", "with", "and", "or", "so", "not", "this", "that", "it", "its",
        "as", "be", "has", "have", "which", "but", "at", "by", "from"
    }
    return {w for w in words if w not in stopwords and len(w) > 2}


def similarity_score(text_a: str, text_b: str) -> float:
    """Jaccard-style overlap between two texts' keyword sets, 0.0 to 1.0."""
    set_a, set_b = normalize(text_a), normalize(text_b)
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return round(len(intersection) / len(union), 3)


def classify_match(score: float) -> str:
    """Buckets a similarity score into a human-readable match category."""
    if score >= 0.35:
        return "likely_correct"
    elif score >= 0.15:
        return "partial_overlap"
    else:
        return "likely_incorrect"


def evaluate(cases_path: str = "cases.json", results_path: str = "results.json") -> dict:
    with open(cases_path) as f:
        cases = json.load(f)
    with open(results_path) as f:
        results = json.load(f)

    cases_by_id = {c["case_id"]: c for c in cases}
    results_by_id = {r["case_id"]: r for r in results}

    per_case = []
    category_stats = defaultdict(lambda: {"total": 0, "likely_correct": 0, "partial_overlap": 0, "likely_incorrect": 0, "parse_errors": 0})

    for case_id, case in cases_by_id.items():
        result = results_by_id.get(case_id)
        category = case["category"]
        category_stats[category]["total"] += 1

        if result is None:
            per_case.append({"case_id": case_id, "category": category, "status": "missing_result"})
            continue

        if result.get("_parse_status") != "ok":
            category_stats[category]["parse_errors"] += 1
            per_case.append({
                "case_id": case_id,
                "category": category,
                "status": "parse_error",
                "error": result.get("_error"),
            })
            continue

        gt_root_cause = case["ground_truth"]["root_cause"]
        ai_root_cause = result.get("root_cause", "")

        score = similarity_score(gt_root_cause, ai_root_cause)
        match = classify_match(score)
        category_stats[category][match] += 1

        per_case.append({
            "case_id": case_id,
            "category": category,
            "status": "evaluated",
            "match": match,
            "similarity_score": score,
            "ai_confidence": result.get("confidence"),
            "ground_truth_root_cause": gt_root_cause,
            "ai_root_cause": ai_root_cause,
        })

    # Overall summary
    total_evaluated = sum(1 for c in per_case if c["status"] == "evaluated")
    total_likely_correct = sum(1 for c in per_case if c.get("match") == "likely_correct")
    total_partial = sum(1 for c in per_case if c.get("match") == "partial_overlap")
    total_incorrect = sum(1 for c in per_case if c.get("match") == "likely_incorrect")
    total_parse_errors = sum(1 for c in per_case if c["status"] == "parse_error")

    overall = {
        "total_cases": len(cases),
        "evaluated": total_evaluated,
        "likely_correct": total_likely_correct,
        "partial_overlap": total_partial,
        "likely_incorrect": total_incorrect,
        "parse_errors": total_parse_errors,
        "accuracy_pct": round(100 * total_likely_correct / total_evaluated, 1) if total_evaluated else 0.0,
    }

    return {
        "overall": overall,
        "by_category": dict(category_stats),
        "per_case": per_case,
    }


if __name__ == "__main__":
    report = evaluate("cases.json", "results.json")

    print("=== OVERALL ===")
    for k, v in report["overall"].items():
        print(f"{k}: {v}")

    print("\n=== BY CATEGORY ===")
    for category, stats in report["by_category"].items():
        print(f"{category}: {stats}")

    with open("evaluation_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print("\nSaved full report to evaluation_report.json")
