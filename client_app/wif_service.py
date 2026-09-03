from __future__ import annotations

import base64
import json
import os
import subprocess
import time
from typing import Any, Dict, Optional
import urllib.request
import urllib.error


def decode_jwt_unverified(token: str) -> Dict[str, Any]:
    """Decodes payload of a JWT without cryptographic verification for inspection."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1]
        # Handle base64 padding
        padded = payload + "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
        return json.loads(decoded)
    except Exception:
        return {}


class WifService:
    """Service to handle Google Cloud Workload Identity Federation (Direct Principal Access)."""

    def __init__(
        self,
        project_number: Optional[str] = None,
        pool_id: Optional[str] = None,
        provider_id: Optional[str] = None,
    ):
        self.project_number = project_number or os.environ.get("PROJECT_NUMBER", "")
        self.pool_id = pool_id or os.environ.get("GCP_WIF_POOL_ID", "")
        self.provider_id = provider_id or os.environ.get("GCP_WIF_PROVIDER_ID", "")

    def build_audience(self, pool_id: str, provider_id: str) -> str:
        """Constructs audience for either Workforce Pools or Workload Identity Pools."""
        is_workforce = (
            "workforce" in pool_id.lower()
            or "workforce" in provider_id.lower()
            or os.environ.get("IS_WORKFORCE_POOL", "").lower() in ("true", "1", "yes")
        )
        clean_pool = pool_id.split("/")[-1].strip()
        clean_provider = provider_id.split("/")[-1].strip()

        if is_workforce:
            return f"//iam.googleapis.com/locations/global/workforcePools/{clean_pool}/providers/{clean_provider}"
        else:
            return (
                f"//iam.googleapis.com/projects/{self.project_number}/locations/global/"
                f"workloadIdentityPools/{clean_pool}/providers/{clean_provider}"
            )

    @property
    def audience(self) -> str:
        return self.build_audience(self.pool_id, self.provider_id)

    def build_full_principal(self, pool_id: str, subject: str) -> str:
        """Constructs canonical Google Cloud IAM full principal URI for WIF."""
        is_workforce = (
            "workforce" in pool_id.lower()
            or os.environ.get("IS_WORKFORCE_POOL", "").lower() in ("true", "1", "yes")
        )
        clean_pool = pool_id.split("/")[-1].strip()
        if is_workforce:
            return f"principal://iam.googleapis.com/locations/global/workforcePools/{clean_pool}/subject/{subject}"
        else:
            return (
                f"principal://iam.googleapis.com/projects/{self.project_number}/locations/global/"
                f"workloadIdentityPools/{clean_pool}/subject/{subject}"
            )

    def exchange_token(
        self,
        entra_token: str,
        pool_id: Optional[str] = None,
        provider_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Exchanges a Microsoft Entra ID JWT for a Google Cloud STS federated access token
        using Direct Principal Access.
        """
        active_pool = pool_id or self.pool_id
        active_provider = provider_id or self.provider_id
        active_audience = self.build_audience(active_pool, active_provider)

        claims = decode_jwt_unverified(entra_token)
        principal_email = (
            claims.get("preferred_username")
            or claims.get("email")
            or claims.get("upn")
            or claims.get("sub")
            or "unidentified-principal"
        )
        full_principal = self.build_full_principal(active_pool, principal_email)

        sts_url = "https://sts.googleapis.com/v1/token"
        payload = {
            "audience": active_audience,
            "grantType": "urn:ietf:params:oauth:grant-type:token-exchange",
            "requestedTokenType": "urn:ietf:params:oauth:token-type:access_token",
            "scope": "https://www.googleapis.com/auth/cloud-platform",
            "subjectTokenType": "urn:ietf:params:oauth:token-type:jwt",
            "subjectToken": entra_token,
        }

        req = urllib.request.Request(
            sts_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return {
                    "success": True,
                    "access_token": data.get("access_token"),
                    "token_type": data.get("token_type", "Bearer"),
                    "expires_in": data.get("expires_in", 3600),
                    "expires_at": int(time.time()) + data.get("expires_in", 3600),
                    "audience": active_audience,
                    "principal": principal_email,
                    "full_principal": full_principal,
                    "wif_token_used": True,
                    "mode": "live_wif",
                    "claims": claims,
                }
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            return {
                "success": False,
                "error": f"GCP STS returned HTTP {e.code}: {e.reason}",
                "details": err_body,
                "audience": active_audience,
                "principal": principal_email,
                "full_principal": full_principal,
                "wif_token_used": False,
                "claims": claims,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "audience": active_audience,
                "principal": principal_email,
                "full_principal": full_principal,
                "wif_token_used": False,
                "claims": claims,
            }

    def get_dev_fallback_token(self, principal_hint: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieves local ADC access token for smooth testing in case WIF IAM pool
        configuration is being provisioned or tweaked in Cloud Console.
        """
        try:
            token = subprocess.check_output(
                ["gcloud", "auth", "application-default", "print-access-token"],
                stderr=subprocess.DEVNULL,
            ).decode("utf-8").strip()

            real_account = None
            try:
                real_account = subprocess.check_output(
                    ["gcloud", "config", "get-value", "account"],
                    stderr=subprocess.DEVNULL,
                ).decode("utf-8").strip()
            except Exception:
                pass

            actual_user = principal_hint or real_account or "adc-local-caller"
            full_principal = f"principal://goog/subject/{actual_user}" if "@" in actual_user else actual_user

            return {
                "success": True,
                "access_token": token,
                "token_type": "Bearer",
                "expires_in": 3600,
                "expires_at": int(time.time()) + 3600,
                "audience": self.audience,
                "principal": actual_user,
                "full_principal": full_principal,
                "wif_token_used": False,
                "mode": "dev_adc_simulation",
                "message": "Using local ADC token for simulation mode (WIF token was NOT used).",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to get ADC fallback token: {e}",
            }
