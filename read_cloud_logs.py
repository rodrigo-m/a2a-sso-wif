#!/usr/bin/env python3
"""
Cloud Logging utility for Google Cloud Agent Runtime.

Fetches and formats real-time logs from Cloud Logging for the deployed
Vertex AI Reasoning Engine / ADK Agent.
"""

import os
import sys
import json
import urllib.request
import subprocess
from dotenv import load_dotenv

load_dotenv()

PROJECT_ID = os.environ.get("PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
if not PROJECT_ID:
    try:
        PROJECT_ID = subprocess.check_output(
            ["gcloud", "config", "get-value", "project"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
    except Exception:
        PROJECT_ID = ""
LOCATION = os.environ.get("LOCATION") or os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")


def get_access_token() -> str:
    return subprocess.check_output(
        ["gcloud", "auth", "application-default", "print-access-token"],
        stderr=subprocess.DEVNULL
    ).decode("utf-8").strip()


def get_reasoning_engine_id(agent_dir: str = "a2a_agent") -> str:
    try:
        cmd = [sys.executable, "get_agent_id.py", "--get-id", agent_dir]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode("utf-8").strip()
        if out:
            return out
    except Exception:
        pass
    return ""


def main():
    agent_dir = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].isdigit() else "a2a_agent"
    page_size = int(sys.argv[2]) if len(sys.argv) > 2 else (int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 25)
    engine_id = get_reasoning_engine_id(agent_dir)

    print("==================================================================")
    print("   Google Cloud Agent Runtime — Live Cloud Logs Viewer            ")
    print("==================================================================")
    print(f"Project ID:           {PROJECT_ID}")
    print(f"Reasoning Engine ID:  {engine_id or 'All Engines'}")
    print("==================================================================\n")

    token = get_access_token()
    url = "https://logging.googleapis.com/v2/entries:list"

    log_filter = (
        f'resource.type="aiplatform.googleapis.com/ReasoningEngine" '
        f'OR resource.labels.reasoning_engine_id="{engine_id}" '
        f'OR jsonPayload.reasoning_engine_id="{engine_id}"'
    ) if engine_id else 'resource.type="aiplatform.googleapis.com/ReasoningEngine"'

    payload = {
        "resourceNames": [f"projects/{PROJECT_ID}"],
        "filter": log_filter,
        "orderBy": "timestamp desc",
        "pageSize": page_size
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            entries = data.get("entries", [])
            if not entries:
                print("No log entries found.")
                return

            print(f"Displaying latest {len(entries)} log entries (chronological order):\n")
            for entry in reversed(entries):
                ts = entry.get("timestamp", "")
                severity = entry.get("severity", "INFO")
                msg = entry.get("textPayload")
                if not msg and "jsonPayload" in entry:
                    json_p = entry["jsonPayload"]
                    msg = json_p.get("message") or json.dumps(json_p)
                print(f"[{ts}] [{severity:5s}] {msg}")
    except Exception as e:
        print(f"Error fetching Cloud Logs: {e}")

if __name__ == "__main__":
    main()
