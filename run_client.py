#!/usr/bin/env python3
"""
Launcher script for A2A SSO & WIF Client Web Application.
"""

import os
import sys
import uvicorn
from dotenv import load_dotenv

load_dotenv()

PORT = int(os.environ.get("PORT", "8000"))
HOST = os.environ.get("HOST", "0.0.0.0")

if __name__ == "__main__":
    print("==================================================================")
    print("   Starting A2A SSO & GCP Workload Identity Federation App        ")
    print("==================================================================")
    print(f"Host:           http://localhost:{PORT}")
    print(f"Project:        {os.environ.get('GOOGLE_CLOUD_PROJECT', 'Not configured')}")
    print(f"Region:         {os.environ.get('GOOGLE_CLOUD_LOCATION', 'us-central1')}")
    print(f"WIF Pool:       {os.environ.get('GCP_WIF_POOL_ID', 'Not configured')}")
    print(f"Agent Engine:   {os.environ.get('REASONING_ENGINE_ID', 'Not configured')}")
    print("==================================================================")
    print(f"🌐 Open your browser at: http://localhost:{PORT}")
    print("==================================================================\n")

    uvicorn.run("client_app.main:app", host=HOST, port=PORT, reload=True)
