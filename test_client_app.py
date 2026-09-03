#!/usr/bin/env python3
"""
Automated tests for A2A SSO & WIF Client Application endpoints.
"""

import sys
import subprocess
from fastapi.testclient import TestClient
from dotenv import load_dotenv

load_dotenv()

from client_app.main import app

client = TestClient(app)


def test_health():
    print("Testing GET /api/health...")
    resp = client.get("/api/health")
    assert resp.status_code == 200, f"Health check failed: {resp.text}"
    data = resp.json()
    assert data["status"] == "HEALTHY"
    print("✅ Health check passed!")


def test_config():
    print("Testing GET /api/config...")
    resp = client.get("/api/config")
    assert resp.status_code == 200, f"Config check failed: {resp.text}"
    data = resp.json()
    assert "project_number" in data
    assert "location" in data
    assert "wif_pool_id" in data
    print(f"✅ Config check passed: project_number={data['project_number']}, pool={data['wif_pool_id']}")


def test_wif_simulation():
    print("Testing POST /api/wif/exchange (Simulation Mode)...")
    payload = {
        "entra_token": "fake.jwt.token",
        "use_dev_fallback": True,
        "principal_hint": "user@example.com"
    }
    resp = client.post("/api/wif/exchange", json=payload)
    assert resp.status_code == 200, f"WIF exchange failed: {resp.text}"
    data = resp.json()
    assert data["success"] is True
    assert "access_token" in data
    assert "full_principal" in data
    assert data["wif_token_used"] is False
    assert data["principal"] == "user@example.com"
    assert data["full_principal"] == "principal://goog/subject/user@example.com"
    print(f"✅ WIF exchange simulation passed! Acquired token for {data['principal']} (WIF used: {data['wif_token_used']})")


def test_wif_live_rejection_on_invalid_token():
    print("Testing POST /api/wif/exchange with invalid token (Error Handling)...")
    payload = {
        "entra_token": "invalid.jwt.token",
        "use_dev_fallback": False,
        "pool_id": "test-wif-pool",
        "provider_id": "test-provider"
    }
    resp = client.post("/api/wif/exchange", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "error" in data
    assert "full_principal" in data
    print(f"✅ WIF error handling verified: {data['error']}")


def test_agent_principal_resolution():
    print("Testing a2a_agent principal resolution logic...")
    from a2a_agent.agent import resolve_caller_principal
    from unittest.mock import MagicMock

    # 1. No user_id provided - must NOT return fake principal
    mock_ctx_empty = MagicMock()
    mock_ctx_empty.user_id = None
    mock_ctx_empty.session.user_id = None
    res = resolve_caller_principal(mock_ctx_empty)
    assert res["authenticated"] is False
    assert res["authenticated_user"] is None
    assert res["full_principal"] is None
    assert res["wif_token_used"] is False

    # 2. WIF Workforce Pool principal provided
    mock_ctx_wif = MagicMock()
    wif_p = "principal://iam.googleapis.com/locations/global/workforcePools/test-wif-pool/subject/alice@example.com"
    mock_ctx_wif.user_id = wif_p
    res = resolve_caller_principal(mock_ctx_wif)
    assert res["authenticated"] is True
    assert res["authenticated_user"] == "alice@example.com"
    assert res["full_principal"] == wif_p
    assert res["wif_token_used"] is True
    assert "Workforce Identity Federation" in res["authorization_mechanism"]

    # 3. ADC / Google user principal provided
    mock_ctx_adc = MagicMock()
    adc_p = "principal://goog/subject/bob@example.com"
    mock_ctx_adc.user_id = adc_p
    res = resolve_caller_principal(mock_ctx_adc)
    assert res["authenticated"] is True
    assert res["authenticated_user"] == "bob@example.com"
    assert res["full_principal"] == adc_p
    assert res["wif_token_used"] is False
    assert "Application Default Credentials" in res["authorization_mechanism"]

    # 4. Direct username or demo user provided
    mock_ctx_direct = MagicMock()
    mock_ctx_direct.user_id = "api_user_demo"
    res = resolve_caller_principal(mock_ctx_direct)
    assert res["authenticated"] is True
    assert res["authenticated_user"] == "api_user_demo"
    assert res["full_principal"] == "api_user_demo"
    assert res["wif_token_used"] is False

    print("✅ Agent principal resolution verified: zero fake principals, correct WIF detection & full principal!")


def main():
    print("==================================================================")
    print("   Running Automated Client App Endpoint Tests                    ")
    print("==================================================================")
    test_health()
    test_config()
    test_wif_simulation()
    test_wif_live_rejection_on_invalid_token()
    test_agent_principal_resolution()
    print("==================================================================")
    print("✅ All Client App Tests Passed Successfully!")
    print("==================================================================")


if __name__ == "__main__":
    main()
