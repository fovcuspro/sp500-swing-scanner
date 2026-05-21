"""
healthcheck.py
Runs before scanner.py. Detects stale or missing results from the previous scan.
Writes health.json which the dashboard reads to show a warning banner.
"""

import json
import logging
import os
from datetime import date, datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

RESULTS_FILE = "results.json"
HEALTH_FILE  = "health.json"

def check() -> dict:
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    health = {
        "checked_at": now_utc,
        "status": "ok",    # ok | stale | missing | error
        "issues": [],
        "last_scan_date": None,
        "last_setup_count": 0,
    }

    if not os.path.exists(RESULTS_FILE):
        health["status"]  = "missing"
        health["issues"].append("results.json not found — scanner may not have run yet")
        return health

    try:
        with open(RESULTS_FILE) as f:
            data = json.load(f)

        scan_date_str = data.get("scan_date", "")
        health["last_scan_date"]   = scan_date_str
        health["last_setup_count"] = len(data.get("top_setups", []))

        if scan_date_str:
            scan_date = date.fromisoformat(scan_date_str)
            days_old  = (date.today() - scan_date).days
            # Allow up to 3 days old (accounts for weekends + Monday)
            if days_old > 3:
                health["status"] = "stale"
                health["issues"].append(f"Last scan was {days_old} days ago ({scan_date_str})")

        if not data.get("top_setups"):
            health["issues"].append("Previous scan returned 0 setups")

    except Exception as e:
        health["status"] = "error"
        health["issues"].append(f"Could not parse results.json: {e}")

    return health

def main():
    health = check()
    with open(HEALTH_FILE, "w") as f:
        json.dump(health, f, indent=2)
    log.info(f"Health check: status={health['status']} issues={health['issues']}")

if __name__ == "__main__":
    main()
