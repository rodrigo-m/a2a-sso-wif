from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Load environment variables
load_dotenv()

from client_app.wif_service import WifService
from client_app.agent_engine_client import AgentEngineClient

app = FastAPI(
    title="Agent-to-Agent SSO & WIF Client",
    description="Local web app demonstrating Microsoft Entra ID SSO, GCP Workload Identity Federation (Direct Principal Access), and Vertex AI Agent Runtime interactions.",
    version="1.0.0",
)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static directory setup
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

wif_service = WifService()
agent_client = AgentEngineClient()


class WifExchangeRequest(BaseModel):
    entra_token: str
    pool_id: Optional[str] = None
    provider_id: Optional[str] = None
    use_dev_fallback: Optional[bool] = False
    principal_hint: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    token: str
    user_id: Optional[str] = None
    full_principal: Optional[str] = None
    wif_token_used: Optional[bool] = None
    session_id: Optional[str] = None


@app.get("/")
async def get_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(str(index_file))


@app.get("/api/config")
async def get_config():
    """Returns runtime client configuration for MSAL and WIF."""
    load_dotenv(override=True)
    return {
        "entra_client_id": os.environ.get("ENTRA_CLIENT_ID", "").strip(),
        "entra_tenant_id": os.environ.get("ENTRA_TENANT_ID", "").strip(),
        "entra_redirect_uri": os.environ.get("ENTRA_REDIRECT_URI", "http://localhost:8000").strip(),
        "project_id": (os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("PROJECT_ID", "")).strip(),
        "project_number": os.environ.get("PROJECT_NUMBER", "").strip(),
        "location": os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1").strip(),
        "wif_pool_id": os.environ.get("GCP_WIF_POOL_ID", "").strip(),
        "wif_provider_id": os.environ.get("GCP_WIF_PROVIDER_ID", "").strip(),
        "reasoning_engine_id": os.environ.get("REASONING_ENGINE_ID", "").strip(),
        "target_endpoint": agent_client.endpoint_url,
    }



@app.post("/api/wif/exchange")
async def exchange_token(req: WifExchangeRequest):
    """
    Exchanges Entra ID token for a Google Cloud STS token (Direct Principal Access).
    """
    load_dotenv(override=True)
    if req.use_dev_fallback:
        res = wif_service.get_dev_fallback_token(principal_hint=req.principal_hint)
        return res

    pool = req.pool_id or os.environ.get("GCP_WIF_POOL_ID", "").strip()
    provider = req.provider_id or os.environ.get("GCP_WIF_PROVIDER_ID", "").strip()

    res = wif_service.exchange_token(
        entra_token=req.entra_token,
        pool_id=pool,
        provider_id=provider,
    )
    print(f"\n[GCP STS Token Exchange Attempt]")
    print(f"Audience:       {res.get('audience')}")
    print(f"Success:        {res.get('success')}")
    print(f"Full Principal: {res.get('full_principal')}")
    print(f"WIF Used:       {res.get('wif_token_used')}")
    if not res.get("success"):
        print(f"Error:          {res.get('error')}")
        print(f"Details:        {res.get('details')}\n")
    return res



@app.post("/api/chat")
async def chat_stream(req: ChatRequest):
    """
    Streams multi-turn chat responses from the deployed Reasoning Engine on Agent Runtime.
    """
    if not req.token:
        raise HTTPException(status_code=401, detail="Authentication token required")

    invoked_principal = req.full_principal or req.user_id
    if not invoked_principal:
        raise HTTPException(status_code=400, detail="Caller principal (user_id or full_principal) is required")

    async def event_generator():
        async for event in agent_client.stream_query(
            message=req.message,
            auth_token=req.token,
            user_id=invoked_principal,
            session_id=req.session_id,
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/health")
async def health_check():
    return {
        "status": "HEALTHY",
        "app": "a2a-sso-client",
        "reasoning_engine_id": agent_client.reasoning_engine_id,
    }
