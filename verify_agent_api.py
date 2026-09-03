#!/usr/bin/env python3
"""
API Verification Script for Deployed ADK Agent.

Tests the deployed Google Cloud Agent Runtime (Vertex AI Reasoning Engine) endpoint:
  - Turn 1: Initial Greeting / Capability check.
  - Turn 2: Agent Tool Execution / Status check.
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
    """Retrieve Application Default Credentials access token."""
    return subprocess.check_output(
        ["gcloud", "auth", "application-default", "print-access-token"],
        stderr=subprocess.DEVNULL
    ).decode("utf-8").strip()


def get_deployed_engine_name(agent_dir: str = "a2a_agent") -> str:
    """Query Vertex AI to get the active Reasoning Engine resource name."""
    token = get_access_token()
    url = f"https://{LOCATION}-aiplatform.googleapis.com/v1beta1/projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        engines = data.get("reasoningEngines", [])
        for e in engines:
            if e.get("displayName") in [agent_dir, " ".join(word.capitalize() for word in agent_dir.split("_"))]:
                return e.get("name")
        if engines:
            return engines[0].get("name")
    raise RuntimeError(f"No deployed Reasoning Engine found in project {PROJECT_ID} / {LOCATION}")


def query_deployed_agent(engine_name: str, message: str, user_id: str = "api_user_demo") -> dict:
    """Send an API query to the deployed Reasoning Engine in Agent Runtime."""
    token = get_access_token()
    url = f"https://{LOCATION}-aiplatform.googleapis.com/v1beta1/{engine_name}:streamQuery"
    
    payload = {
        "classMethod": "async_stream_query",
        "input": {
            "user_id": user_id,
            "message": message,
        }
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
    
    text_responses = []
    tool_calls = []
    tool_responses = []

    with urllib.request.urlopen(req) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8").strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                content = event.get("content", {})
                parts = content.get("parts", [])
                for p in parts:
                    if "text" in p and p["text"]:
                        text_responses.append(p["text"])
                    if "function_call" in p:
                        tool_calls.append(p["function_call"])
                    if "function_response" in p:
                        tool_responses.append(p["function_response"])
            except Exception:
                pass
                
    return {
        "text": "".join(text_responses).strip(),
        "tool_calls": tool_calls,
        "tool_responses": tool_responses
    }


def main():
    agent_dir = sys.argv[1] if len(sys.argv) > 1 else "a2a_agent"
    print("==================================================================")
    print("   Google Cloud Agent Runtime API Verification                    ")
    print("==================================================================")
    print(f"Project ID: {PROJECT_ID}")
    print(f"Location:   {LOCATION}")
    
    try:
        engine_name = get_deployed_engine_name(agent_dir)
        print(f"Target Reasoning Engine: {engine_name}")
    except Exception as e:
        print(f"Error resolving deployed engine: {e}")
        sys.exit(1)

    print("\n------------------------------------------------------------------")
    print("TURN 1: Initial Greeting with 'Hi' (SSO & Full WIF Principal Check)")
    print("------------------------------------------------------------------")
    prompt1 = "Hi"
    wif_pool = os.environ.get("GCP_WIF_POOL_ID", "default-wif-pool")
    caller_email = os.environ.get("TEST_CALLER_EMAIL", "user@example.com")
    test_user = f"principal://iam.googleapis.com/locations/global/workforcePools/{wif_pool}/subject/{caller_email}"
    print(f"Caller Full Principal: '{test_user}'")
    print(f"User Prompt:           '{prompt1}'")
    res1 = query_deployed_agent(engine_name, prompt1, user_id=test_user)
    if res1["tool_calls"]:
        print(f"-> [Tool Call]: {', '.join([c.get('name') for c in res1['tool_calls']])}")
    if res1["tool_responses"]:
        tool_out = res1['tool_responses'][0].get('response', {})
        print(f"-> [Tool Output]: {json.dumps(tool_out, indent=2)}")
        print(f"-> [Verified Principal]: {tool_out.get('authenticated_user')}")
        print(f"-> [Full Principal]:     {tool_out.get('full_principal')}")
        print(f"-> [WIF Token Used]:     {tool_out.get('wif_token_used')}")
    print(f"\nAgent Reply:\n{res1['text']}")

    print("\n------------------------------------------------------------------")
    print("TURN 2: Tool Execution (Status Check with Full Principal)")
    print("------------------------------------------------------------------")
    prompt2 = "What is your current status and runtime environment?"
    print(f"User Prompt: '{prompt2}'")
    res2 = query_deployed_agent(engine_name, prompt2, user_id=test_user)
    if res2["tool_calls"]:
        print(f"-> [Tool Call]: {', '.join([c.get('name') for c in res2['tool_calls']])}")
    if res2["tool_responses"]:
        tool_out2 = res2['tool_responses'][0].get('response', {})
        print(f"-> [Tool Output]: {json.dumps(tool_out2, indent=2)}")
        print(f"-> [Verified Caller]:    {tool_out2.get('caller')}")
        print(f"-> [Full Principal]:     {tool_out2.get('full_principal')}")
        print(f"-> [WIF Token Used]:     {tool_out2.get('wif_token_used')}")
    print(f"\nAgent Reply:\n{res2['text']}")

    print("\n==================================================================")
    print("✅ API Verification Completed Successfully!")
    print("==================================================================")


if __name__ == "__main__":
    main()
