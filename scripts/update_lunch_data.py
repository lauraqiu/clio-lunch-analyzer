#!/usr/bin/env python3
"""
Export lunch data to JSON for scheduled refresh (e.g. GitHub Actions).
Run from repo root: python scripts/update_lunch_data.py
Writes data/lunch_data.json. Set SLACK_TOKEN (or SLACK_COOKIE) and CHANNEL_ID in env.
"""
import json
import os
import sys

# Run from repo root so lunch_analyzer is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lunch_analyzer import analyze_lunches


def main():
    days_back = int(os.environ.get("DAYS_BACK", "30"))
    out_dir = os.environ.get("LUNCH_DATA_DIR", "data")
    out_path = os.path.join(out_dir, "lunch_data.json")

    data = analyze_lunches(days_back=days_back)
    if not data:
        print("No lunch data returned.")
        sys.exit(1)

    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Wrote {len(data)} lunches to {out_path}")


if __name__ == "__main__":
    main()
