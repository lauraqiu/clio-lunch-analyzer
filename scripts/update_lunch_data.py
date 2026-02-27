#!/usr/bin/env python3
"""
Export lunch data to JSON for scheduled refresh (e.g. GitHub Actions).
Run from repo root: python scripts/update_lunch_data.py
Writes data/lunch_data.json. Set SLACK_TOKEN (or SLACK_COOKIE) and CHANNEL_ID in env.
"""
import json
import os
import sys
from datetime import datetime

# Run from repo root so lunch_analyzer is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lunch_analyzer import analyze_lunches


def to_serializable(obj):
    """Recursively convert data to JSON-serializable types."""
    if isinstance(obj, datetime):
        return obj.strftime("%Y-%m-%d")
    if isinstance(obj, dict):
        return {k: to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_serializable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def main():
    days_back = int(os.environ.get("DAYS_BACK", "30"))
    out_dir = os.environ.get("LUNCH_DATA_DIR", "data")
    out_path = os.path.join(out_dir, "lunch_data.json")

    data = analyze_lunches(days_back=days_back)
    if not data:
        print("No lunch data returned.")
        sys.exit(1)

    # Build a clean copy with only JSON-serializable values (no datetime objects)
    data_clean = to_serializable(data)

    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(data_clean, f, indent=2)

    print(f"Wrote {len(data)} lunches to {out_path}")


if __name__ == "__main__":
    main()
