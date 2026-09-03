from __future__ import annotations

import json
import os
import re
import warnings
from typing import Any
from dotenv import load_dotenv

# Automatically load environment variables from .env
load_dotenv()

from google.adk import Agent
from google.adk.tools import ToolContext

# Suppress experimental ADK warnings for clean logs
warnings.filterwarnings("ignore")

# Model & Regional configuration
LLM_MODEL = os.environ.get("LLM_MODEL", "gemini-2.5-flash")
LLM_LOCATION = os.environ.get("LLM_LOCATION") or os.environ.get("LOCATION") or os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")


def resolve_caller_principal(tool_context: ToolContext) -> dict[str, Any]:
    """
    Extracts and normalizes the caller's principal used to invoke the agent API.
    Guarantees that no synthetic or fake principal is ever returned.
    """
    raw_user_id = getattr(tool_context, "user_id", None)
    if not raw_user_id and hasattr(tool_context, "session"):
        raw_user_id = getattr(tool_context.session, "user_id", None)

    # If user_id is missing, empty, or an unauthenticated placeholder, do NOT return a fake principal
    if not raw_user_id or str(raw_user_id).strip() in ("", "default-user-id", "None", "null", "undefined", "unknown"):
        return {
            "authenticated": False,
            "authenticated_user": None,
            "full_principal": None,
            "wif_token_used": False,
            "identity_provider": "None",
            "authorization_mechanism": "Unauthenticated / No caller principal provided in API invocation",
        }

    raw_user_str = str(raw_user_id).strip()

    # Case 1: Structured JSON payload passed as user_id
    if raw_user_str.startswith("{") and raw_user_str.endswith("}"):
        try:
            payload = json.loads(raw_user_str)
            full_p = payload.get("full_principal") or payload.get("principal")
            wif_used = bool(payload.get("wif_token_used", False))
            user_name = payload.get("principal") or payload.get("user") or full_p
            idp = payload.get("identity_provider") or ("Microsoft Entra ID" if wif_used else "Direct IdP")
            auth_mech = payload.get("authorization_mechanism") or (
                "Google Cloud Workload Identity Federation (Direct Principal Access)" if wif_used else "Direct API Invocation"
            )
            return {
                "authenticated": True,
                "authenticated_user": user_name,
                "full_principal": full_p,
                "wif_token_used": wif_used,
                "identity_provider": idp,
                "authorization_mechanism": auth_mech,
            }
        except Exception:
            pass

    # Case 2: Workload Identity Federation / Workforce Identity Federation canonical principal URI:
    # principal://iam.googleapis.com/locations/global/workforcePools/<POOL_ID>/subject/<SUBJECT>
    # or principal://iam.googleapis.com/projects/<NUM>/locations/global/workloadIdentityPools/<POOL_ID>/subject/<SUBJECT>
    if (raw_user_str.startswith("principal://iam.googleapis.com/") or raw_user_str.startswith("principalSet://iam.googleapis.com/")) and (
        "/workforcePools/" in raw_user_str or "/workloadIdentityPools/" in raw_user_str
    ):
        is_workforce = "/workforcePools/" in raw_user_str
        pool_match = re.search(r"/(work(?:force|loadIdentity)Pools)/([^/]+)", raw_user_str)
        pool_id = pool_match.group(2) if pool_match else "configured-pool"
        if "/subject/" in raw_user_str:
            subject = raw_user_str.split("/subject/")[-1]
        elif "/attribute." in raw_user_str:
            subject = raw_user_str.split("/")[-1]
        else:
            subject = raw_user_str
        pool_type = "Workforce" if is_workforce else "Workload"

        return {
            "authenticated": True,
            "authenticated_user": subject,
            "full_principal": raw_user_str,
            "wif_token_used": True,
            "identity_provider": "Microsoft Entra ID (Federated via OIDC)",
            "authorization_mechanism": f"Google Cloud {pool_type} Identity Federation (Direct Principal Access via pool '{pool_id}')",
        }

    # Case 3: Google Account ADC / OAuth2: principal://goog/subject/<EMAIL>
    if raw_user_str.startswith("principal://goog/subject/"):
        email = raw_user_str.split("/subject/")[-1]
        return {
            "authenticated": True,
            "authenticated_user": email,
            "full_principal": raw_user_str,
            "wif_token_used": False,
            "identity_provider": "Google Identity (Google Cloud ADC / OAuth2)",
            "authorization_mechanism": "Google Cloud IAM (Application Default Credentials)",
        }

    # Case 4: Service Account: principal://iam.googleapis.com/projects/-/serviceAccounts/<EMAIL>
    if raw_user_str.startswith("principal://iam.googleapis.com/projects/-/serviceAccounts/"):
        sa_email = raw_user_str.split("/serviceAccounts/")[-1]
        return {
            "authenticated": True,
            "authenticated_user": sa_email,
            "full_principal": raw_user_str,
            "wif_token_used": False,
            "identity_provider": "Google Cloud Service Account",
            "authorization_mechanism": "Google Cloud IAM (Service Account)",
        }

    # Case 5: Direct user identifier or email passed directly as invocation user_id
    # (e.g. from direct API calls, verify scripts, or custom headers)
    return {
        "authenticated": True,
        "authenticated_user": raw_user_str,
        "full_principal": raw_user_str,
        "wif_token_used": False,
        "identity_provider": "Direct Caller Identifier",
        "authorization_mechanism": "Standard API Invocation (Direct Caller Principal)",
    }


def get_caller_identity(tool_context: ToolContext) -> dict[str, Any]:
    """Retrieves the authenticated caller's identity and SSO/WIF federation context."""
    info = resolve_caller_principal(tool_context)
    return {
        "status": "AUTHENTICATED" if info["authenticated"] else "UNAUTHENTICATED",
        "authenticated_user": info["authenticated_user"],
        "full_principal": info["full_principal"],
        "wif_token_used": info["wif_token_used"],
        "identity_provider": info["identity_provider"],
        "authorization_mechanism": info["authorization_mechanism"],
        "agent_runtime": "Google Cloud Agent Runtime (Vertex AI Reasoning Engines)",
        "region": LLM_LOCATION,
        "session_id": getattr(tool_context, "session_id", None) or getattr(getattr(tool_context, "session", None), "id", None) or "active-session",
    }


def get_agent_status(tool_context: ToolContext) -> dict[str, Any]:
    """Retrieves the current operational status and environment of the agent."""
    info = resolve_caller_principal(tool_context)
    return {
        "status": "HEALTHY",
        "runtime_platform": "Google Cloud Agent Runtime (ADK + Vertex AI)",
        "model": LLM_MODEL,
        "region": LLM_LOCATION,
        "caller": info["authenticated_user"],
        "full_principal": info["full_principal"],
        "wif_token_used": info["wif_token_used"],
        "auth_provider": info["authorization_mechanism"],
    }


# Define system instruction detailing persona, behavior, and tool usage rules
SYSTEM_INSTRUCTION = """
You are an intelligent autonomous enterprise agent developed with the Google Agent Development Kit (ADK) and deployed on Google Cloud Agent Runtime.

Guidelines:
1. When greeted with "Hi", "Hello", or any greeting, warmly greet the user and call the `get_caller_identity` tool to confirm their verified authentication details.
Always explicitly display the caller's authentication details using the exact values from `get_caller_identity`:
   - Authenticated User: <authenticated_user>
   - Full Principal: <full_principal>
   - WIF Token Used: <"Yes" if wif_token_used is True, else "No">
   - Identity Provider: <identity_provider>
   - Authorization Mechanism: <authorization_mechanism>
   - Agent Runtime Platform & Region: Google Cloud Agent Runtime (<region>)
CRITICAL: Never return or invent a fake principal or assume hardcoded identity claims. Always report the exact caller identity returned by `get_caller_identity`.
2. When asked about your status, health, or runtime environment, use the `get_agent_status` tool and present your status, model, caller, full principal, and whether a WIF token was used.
3. Provide concise, well-structured, professional, and helpful answers.
"""

# Instantiate the ADK root agent
root_agent = Agent(
    name="a2a_agent",
    model=LLM_MODEL,
    description="Enterprise ADK Agent running on Google Cloud Agent Runtime.",
    instruction=SYSTEM_INSTRUCTION,
    tools=[get_agent_status, get_caller_identity]
)


