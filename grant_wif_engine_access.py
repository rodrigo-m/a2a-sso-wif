#!/usr/bin/env python3
"""
Grant IAM Permissions to Workload/Workforce Identity Federation (WIF) Principals
on Vertex AI Reasoning Engine (Agent Runtime) and GCP Project.

This script constructs the appropriate IAM principal identifier for attribute-based
access (attribute.email) and applies the required role (roles/aiplatform.user)
directly to the Reasoning Engine resource and/or project level.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()


def get_gcp_access_token() -> str:
    """Retrieve OAuth2 access token via Application Default Credentials (ADC)."""
    try:
        token = subprocess.check_output(
            ["gcloud", "auth", "application-default", "print-access-token"],
            stderr=subprocess.PIPE,
        ).decode("utf-8").strip()
        if token:
            return token
    except Exception:
        pass

    # Fallback to standard gcloud auth token
    try:
        token = subprocess.check_output(
            ["gcloud", "auth", "print-access-token"],
            stderr=subprocess.PIPE,
        ).decode("utf-8").strip()
        if token:
            return token
    except Exception:
        pass

    raise RuntimeError(
        "Could not obtain Google Cloud access token. "
        "Please run 'gcloud auth application-default login' first."
    )


def http_request(
    url: str,
    token: str,
    method: str = "GET",
    body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Sends authenticated JSON HTTP request to Google Cloud APIs."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        try:
            parsed_err = json.loads(err_body)
            msg = parsed_err.get("error", {}).get("message", err_body)
        except Exception:
            msg = err_body
        raise RuntimeError(f"HTTP {e.code} ({e.reason}): {msg}") from e


def build_wif_principal(
    email: str,
    pool_id: str,
    project_number: str,
    is_workforce: bool = True,
    use_subject: bool = False,
    all_users: bool = False,
) -> str:
    """
    Constructs the standard GCP IAM member identifier string.

    Workforce Pools:
      - Attribute: principalSet://iam.googleapis.com/locations/global/workforcePools/<POOL>/attribute.email/<EMAIL>
      - Subject:   principal://iam.googleapis.com/locations/global/workforcePools/<POOL>/subject/<SUBJECT>
      - All Users: principalSet://iam.googleapis.com/locations/global/workforcePools/<POOL>/*

    Workload Pools:
      - Attribute: principalSet://iam.googleapis.com/projects/<NUM>/locations/global/workloadIdentityPools/<POOL>/attribute.email/<EMAIL>
      - Subject:   principal://iam.googleapis.com/projects/<NUM>/locations/global/workloadIdentityPools/<POOL>/subject/<SUBJECT>
      - All Users: principalSet://iam.googleapis.com/projects/<NUM>/locations/global/workloadIdentityPools/<POOL>/*
    """
    clean_pool = pool_id.split("/")[-1].strip()

    if is_workforce:
        prefix = f"iam.googleapis.com/locations/global/workforcePools/{clean_pool}"
    else:
        prefix = f"iam.googleapis.com/projects/{project_number}/locations/global/workloadIdentityPools/{clean_pool}"

    if all_users:
        return f"principalSet://{prefix}/*"
    elif use_subject:
        return f"principal://{prefix}/subject/{email}"
    else:
        # Attribute-based matching (MANDATORY principalSet:// in Google Cloud IAM)
        return f"principalSet://{prefix}/attribute.email/{email}"


def check_and_update_provider_attribute_mapping(
    token: str,
    pool_id: str,
    provider_id: str,
    auto_update: bool = False,
) -> bool:
    """
    Verifies that the Workforce Identity Provider has attribute.email mapped.
    If missing and auto_update is True, patches the provider attributeMapping.
    """
    clean_pool = pool_id.split("/")[-1].strip()
    clean_provider = provider_id.split("/")[-1].strip()
    provider_url = f"https://iam.googleapis.com/v1/locations/global/workforcePools/{clean_pool}/providers/{clean_provider}"

    try:
        provider = http_request(provider_url, token=token, method="GET")
    except Exception as e:
        print(f"⚠️  Could not inspect provider '{clean_provider}': {e}")
        return False

    mapping = provider.get("attributeMapping", {})
    email_attr = mapping.get("attribute.email")

    if email_attr:
        print(f"✅ Provider attribute mapping verified: 'attribute.email' -> '{email_attr}'")
        return True

    print(f"⚠️  Warning: Provider '{clean_provider}' does NOT currently map 'attribute.email'!")
    print(f"   Current mappings: {list(mapping.keys())}")

    if not auto_update:
        print("   -> Run with --update-provider to automatically add 'attribute.email' mapping.")
        return False

    print("🔧 Updating provider attribute mapping to include 'attribute.email'...")
    new_mapping = dict(mapping)
    # CEL expression: use email if available, fallback to preferred_username
    new_mapping["attribute.email"] = "has(assertion.email) ? assertion.email : assertion.preferred_username"

    patch_url = f"{provider_url}?updateMask=attribute_mapping"
    patch_body = {"attributeMapping": new_mapping}
    try:
        res = http_request(patch_url, token=token, method="PATCH", body=patch_body)
        print(f"✅ Provider attributeMapping updated successfully: {res.get('name')}")
        return True
    except Exception as e:
        print(f"❌ Failed to update provider attributeMapping: {e}")
        return False


def get_reasoning_engine_iam_policy(
    token: str,
    project: str,
    location: str,
    engine_id: str,
) -> Dict[str, Any]:
    """Fetches IAM policy directly from the Vertex AI Reasoning Engine resource."""
    url = f"https://{location}-aiplatform.googleapis.com/v1beta1/projects/{project}/locations/{location}/reasoningEngines/{engine_id}:getIamPolicy"
    return http_request(url, token=token, method="POST", body={})


def set_reasoning_engine_iam_policy(
    token: str,
    project: str,
    location: str,
    engine_id: str,
    policy: Dict[str, Any],
) -> Dict[str, Any]:
    """Sets IAM policy directly on the Vertex AI Reasoning Engine resource."""
    url = f"https://{location}-aiplatform.googleapis.com/v1beta1/projects/{project}/locations/{location}/reasoningEngines/{engine_id}:setIamPolicy"
    body = {"policy": policy}
    return http_request(url, token=token, method="POST", body=body)


def get_project_iam_policy(token: str, project_id: str) -> Dict[str, Any]:
    """Fetches GCP project-level IAM policy via Resource Manager API."""
    url = f"https://cloudresourcemanager.googleapis.com/v1/projects/{project_id}:getIamPolicy"
    return http_request(url, token=token, method="POST", body={})


def set_project_iam_policy(
    token: str,
    project_id: str,
    policy: Dict[str, Any],
) -> Dict[str, Any]:
    """Sets GCP project-level IAM policy via Resource Manager API."""
    url = f"https://cloudresourcemanager.googleapis.com/v1/projects/{project_id}:setIamPolicy"
    body = {"policy": policy}
    return http_request(url, token=token, method="POST", body=body)


def add_member_to_policy(
    policy: Dict[str, Any],
    role: str,
    member: str,
) -> bool:
    """Adds member to role in IAM policy. Returns True if modified, False if already present."""
    bindings = policy.setdefault("bindings", [])
    for b in bindings:
        if b.get("role") == role:
            if member in b.get("members", []):
                return False
            b.setdefault("members", []).append(member)
            return True

    bindings.append({"role": role, "members": [member]})
    return True


def remove_member_from_policy(
    policy: Dict[str, Any],
    role: str,
    member: str,
) -> bool:
    """Removes member from role in IAM policy. Returns True if modified."""
    modified = False
    bindings = policy.get("bindings", [])
    for b in bindings:
        if b.get("role") == role:
            members = b.get("members", [])
            if member in members:
                members.remove(member)
                modified = True
    return modified


def main():
    parser = argparse.ArgumentParser(
        description="Grant IAM permissions to WIF principal based on email attribute."
    )
    parser.add_argument(
        "--email",
        default=os.environ.get("USER_EMAIL", ""),
        help="Email attribute of the user (e.g. user@example.com)",
    )
    parser.add_argument(
        "--role",
        default="roles/aiplatform.user",
        help="IAM role to grant (default: roles/aiplatform.user)",
    )
    parser.add_argument(
        "--scope",
        choices=["engine", "project", "both"],
        default="both",
        help="Scope of IAM binding: 'engine' (Reasoning Engine resource), 'project' (GCP Project), or 'both' (default: both)",
    )
    parser.add_argument(
        "--pool-id",
        default=os.environ.get("GCP_WIF_POOL_ID"),
        help="Workforce or Workload Identity Pool ID (default: from .env)",
    )
    parser.add_argument(
        "--provider-id",
        default=os.environ.get("GCP_WIF_PROVIDER_ID"),
        help="WIF Provider ID (default: from .env)",
    )
    parser.add_argument(
        "--engine-id",
        default=os.environ.get("REASONING_ENGINE_ID"),
        help="Vertex AI Reasoning Engine ID (default: from .env)",
    )
    parser.add_argument(
        "--project",
        default=os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("PROJECT_ID"),
        help="Google Cloud Project ID (default: from .env or gcloud config)",
    )
    parser.add_argument(
        "--project-number",
        default=os.environ.get("PROJECT_NUMBER"),
        help="Google Cloud Project Number (default: from .env)",
    )
    parser.add_argument(
        "--location",
        default=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
        help="Google Cloud Region (default: us-central1)",
    )
    parser.add_argument(
        "--workload-pool",
        action="store_true",
        help="Treat pool as Workload Identity Pool instead of Workforce Pool",
    )
    parser.add_argument(
        "--subject",
        action="store_true",
        help="Grant to principal://.../subject/<email> instead of attribute.email",
    )
    parser.add_argument(
        "--all-users",
        action="store_true",
        help="Grant to all users in pool (principalSet://.../*)",
    )
    parser.add_argument(
        "--update-provider",
        action="store_true",
        help="Ensure Workforce Provider maps attribute.email in attributeMapping",
    )
    parser.add_argument(
        "--revoke",
        action="store_true",
        help="Revoke the permission instead of granting it",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Display principal and target without applying changes",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List current IAM policies for Reasoning Engine and Project",
    )

    args = parser.parse_args()

    if not args.list and not args.all_users and not args.email:
        parser.error("the following arguments are required: --email (or specify --all-users or --list)")

    is_workforce = not args.workload_pool and (
        os.environ.get("IS_WORKFORCE_POOL", "true").lower() in ("true", "1", "yes")
    )

    if args.list and not args.email and not args.all_users:
        principal = ""
        principal_display = "N/A (Listing mode)"
    else:
        principal = build_wif_principal(
            email=args.email,
            pool_id=args.pool_id,
            project_number=args.project_number,
            is_workforce=is_workforce,
            use_subject=args.subject,
            all_users=args.all_users,
        )
        principal_display = principal

    resource_name = f"projects/{args.project_number}/locations/{args.location}/reasoningEngines/{args.engine_id}"

    print("==================================================================")
    print("   Grant WIF Principal Access to Vertex AI Reasoning Engine       ")
    print("==================================================================")
    print(f"Pool Type:        {'Workforce Identity Pool' if is_workforce else 'Workload Identity Pool'}")
    print(f"Pool ID:          {args.pool_id}")
    print(f"Provider ID:      {args.provider_id}")
    print(f"Project ID:       {args.project} ({args.project_number})")
    print(f"Location:         {args.location}")
    print(f"Reasoning Engine: {args.engine_id}")
    print(f"Resource Path:    {resource_name}")
    print(f"IAM Role:         {args.role}")
    print(f"Target Principal: {principal_display}")
    print("==================================================================\n")

    token = get_gcp_access_token()

    # 1. Check provider attribute mapping
    if is_workforce:
        check_and_update_provider_attribute_mapping(
            token=token,
            pool_id=args.pool_id,
            provider_id=args.provider_id,
            auto_update=args.update_provider,
        )
        print()

    # 2. List mode
    if args.list:
        print("--- Reasoning Engine IAM Policy ---")
        try:
            engine_policy = get_reasoning_engine_iam_policy(
                token, args.project_number, args.location, args.engine_id
            )
            print(json.dumps(engine_policy, indent=2))
        except Exception as e:
            print(f"Error: {e}")

        print("\n--- Project IAM Policy (Bindings for role) ---")
        try:
            proj_policy = get_project_iam_policy(token, args.project)
            matching = [b for b in proj_policy.get("bindings", []) if b.get("role") == args.role]
            print(json.dumps(matching, indent=2))
        except Exception as e:
            print(f"Error: {e}")
        return

    if args.dry_run:
        print("🔍 Dry Run Mode Enabled. No changes applied.")
        print(f"Would {'revoke' if args.revoke else 'grant'} {args.role} to {principal}")
        print(f"Scope: {args.scope}")
        return

    # 3. Apply to Reasoning Engine
    if args.scope in ("engine", "both"):
        print(f"📡 {'Revoking from' if args.revoke else 'Granting on'} Reasoning Engine resource...")
        try:
            engine_policy = get_reasoning_engine_iam_policy(
                token, args.project_number, args.location, args.engine_id
            )
            if args.revoke:
                changed = remove_member_from_policy(engine_policy, args.role, principal)
            else:
                changed = add_member_to_policy(engine_policy, args.role, principal)

            if changed:
                res = set_reasoning_engine_iam_policy(
                    token, args.project_number, args.location, args.engine_id, engine_policy
                )
                print(f"✅ Successfully updated Reasoning Engine IAM policy!")
                for b in res.get("bindings", []):
                    if b.get("role") == args.role:
                        print(f"   Role: {b.get('role')}")
                        for m in b.get("members", []):
                            marker = " -> [Target]" if m == principal else ""
                            print(f"     - {m}{marker}")
            else:
                print(f"ℹ️  Principal is already {'absent from' if args.revoke else 'present in'} Reasoning Engine IAM policy.")
        except Exception as e:
            print(f"❌ Failed to update Reasoning Engine IAM policy: {e}")

    # 4. Apply to Project
    if args.scope in ("project", "both"):
        print(f"\n📡 {'Revoking from' if args.revoke else 'Granting on'} GCP Project '{args.project}'...")
        try:
            proj_policy = get_project_iam_policy(token, args.project)
            if args.revoke:
                changed = remove_member_from_policy(proj_policy, args.role, principal)
            else:
                changed = add_member_to_policy(proj_policy, args.role, principal)

            if changed:
                set_project_iam_policy(token, args.project, proj_policy)
                print(f"✅ Successfully updated Project IAM policy!")
                print(f"   Granted '{args.role}' to '{principal}' on project '{args.project}'.")
            else:
                print(f"ℹ️  Principal is already {'absent from' if args.revoke else 'present in'} Project IAM policy.")
        except Exception as e:
            print(f"❌ Failed to update Project IAM policy: {e}")

    print("\n==================================================================")
    print("✅ Configuration completed!")
    print(f"Caller Identity: {args.email}")
    print(f"Granted Member:  {principal}")
    print("==================================================================")
    print("\nEquivalent gcloud command for project-level binding:")
    print(f"  gcloud projects {'remove' if args.revoke else 'add'}-iam-policy-binding {args.project} \\")
    print(f"    --role=\"{args.role}\" \\")
    print(f"    --member=\"{principal}\"")
    print("==================================================================")


if __name__ == "__main__":
    main()
