#!/usr/bin/env python3
"""
Serve a2a_agent as a native A2A (Agent-to-Agent) protocol server.

Exposes:
  - GET  /.well-known/agent-card.json (Official A2A AgentCard)
  - POST /a2a/ (A2A JSON-RPC 2.0 interface for tasks & messages)
"""

import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

from a2a_agent.agent import root_agent
from google.adk.a2a.utils.agent_to_a2a import to_a2a

PORT = int(os.environ.get("A2A_PORT", "8001"))
HOST = os.environ.get("A2A_HOST", "0.0.0.0")

app = to_a2a(
    agent=root_agent,
    host=HOST,
    port=PORT,
    protocol="http",
    rpc_path="a2a",
    agent_card="a2a_agent/agent_card.json",
)

if __name__ == "__main__":
    print("==================================================================")
    print("   Starting Local A2A Protocol Server for a2a_agent               ")
    print("==================================================================")
    print(f"Host:                    {HOST}")
    print(f"Port:                    {PORT}")
    print(f"Agent Card URL:          http://localhost:{PORT}/.well-known/agent-card.json")
    print(f"A2A JSON-RPC Endpoint:   http://localhost:{PORT}/a2a/")
    print("==================================================================")
    uvicorn.run(app, host=HOST, port=PORT)
