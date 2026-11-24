"""
NetSage AI - AI Diagnosis Engine
Sends each case to the Groq LLM using the prompt layer, parses the
JSON response, and handles malformed output gracefully.
"""

import os
import json
import time
from dotenv import load_dotenv
from groq import Groq

from prompts import build_messages

load_dotenv()

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

MODEL = "llama-3.3-70b-versatile"  # solid free-tier Groq model for structured JSON tasks

REQUIRED_KEYS = ["root_cause", "osi_layer", "confidence", "evidence", "next_command", "fix_steps"]


def clean_json_response(raw_text: str) -> str:
    """Strips markdown code fences if the model wraps its JSON in them despite instructions."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def diagnose_case(case: dict, rule_flags: list = None, retries: int = 2) -> dict:
    """
    Sends one case to the LLM and returns a parsed diagnosis dict.
    On malformed JSON, retries up to `retries` times before returning an error entry.
    """
    messages = build_messages(case, rule_flags)

    last_error = None
    for attempt in range(retries + 1):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=0.2,
                max_tokens=800,
            )
            raw_text = response.choices[0].message.content
            cleaned = clean_json_response(raw_text)
            parsed = json.loads(cleaned)

            missing = [k for k in REQUIRED_KEYS if k not in parsed]
            if missing:
                raise ValueError(f"Missing keys in response: {missing}")

            parsed["case_id"] = case["case_id"]
            parsed["_raw_response"] = raw_text
            parsed["_parse_status"] = "ok"
            return parsed

        except (json.JSONDecodeError, ValueError) as e:
            last_error = str(e)
            time.sleep(1)  # brief pause before retry
            continue

    # all retries failed — return a structured error entry instead of crashing
    return {
        "case_id": case["case_id"],
        "root_cause": None,
        "osi_layer": None,
        "confidence": 0,
        "evidence": [],
        "next_command": None,
        "fix_steps": [],
        "_raw_response": None,
        "_parse_status": "error",
        "_error": last_error,
    }


def diagnose_all_cases(cases_path: str = "../data/cases.json", rule_flags_by_case: dict = None) -> list:
    """Runs diagnosis on every case in the dataset. Returns a list of diagnosis dicts."""
    with open(cases_path) as f:
        cases = json.load(f)

    results = []
    for case in cases:
        flags = rule_flags_by_case.get(case["case_id"]) if rule_flags_by_case else None
        print(f"Diagnosing {case['case_id']}...")
        result = diagnose_case(case, rule_flags=flags)
        results.append(result)
        status = result["_parse_status"]
        print(f"  -> {status}" + (f" ({result.get('confidence')}% confidence)" if status == "ok" else f" ({result.get('_error')})"))
    return results


if __name__ == "__main__":
    if not os.environ.get("GROQ_API_KEY"):
        print("GROQ_API_KEY not set. Create a .env file with GROQ_API_KEY=your_key_here")
    else:
        with open("../data/cases.json") as f:
            cases = json.load(f)
        # quick single-case test run first
        sample = cases[0]
        result = diagnose_case(sample)
        print(json.dumps(result, indent=2))
