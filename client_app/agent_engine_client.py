from __future__ import annotations

import json
import os
from typing import Any, AsyncGenerator, Dict, Optional
import httpx


class AgentEngineClient:
    """Client for interacting with Google Cloud Agent Runtime (Vertex AI Reasoning Engine)."""

    def __init__(
        self,
        project_number: Optional[str] = None,
        location: Optional[str] = None,
        reasoning_engine_id: Optional[str] = None,
    ):
        self.project_number = project_number or os.environ.get("PROJECT_NUMBER", "")
        self.location = location or os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
        self.reasoning_engine_id = reasoning_engine_id or os.environ.get("REASONING_ENGINE_ID", "")

    @property
    def resource_name(self) -> str:
        return f"projects/{self.project_number}/locations/{self.location}/reasoningEngines/{self.reasoning_engine_id}"

    @property
    def endpoint_url(self) -> str:
        return f"https://{self.location}-aiplatform.googleapis.com/v1beta1/{self.resource_name}:streamQuery"

    async def stream_query(
        self,
        message: str,
        auth_token: str,
        user_id: str,
        session_id: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Sends an asynchronous stream query to the deployed Reasoning Engine in Agent Runtime.
        Yields parsed events (text chunks, tool calls, tool responses).
        """
        payload = {
            "classMethod": "async_stream_query",
            "input": {
                "user_id": user_id,
                "message": message,
            }
        }
        if session_id:
            payload["input"]["session_id"] = session_id

        headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream, application/json",
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", self.endpoint_url, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    err_text = await response.aread()
                    yield {
                        "type": "error",
                        "status_code": response.status_code,
                        "error": f"Agent Runtime returned HTTP {response.status_code}: {err_text.decode('utf-8', errors='ignore')}",
                    }
                    return

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        content = event.get("content", {})
                        parts = content.get("parts", [])
                        for p in parts:
                            if "text" in p and p["text"]:
                                yield {"type": "text", "content": p["text"]}
                            if "function_call" in p:
                                yield {
                                    "type": "tool_call",
                                    "name": p["function_call"].get("name"),
                                    "args": p["function_call"].get("args", {}),
                                }
                            if "function_response" in p:
                                yield {
                                    "type": "tool_response",
                                    "name": p["function_response"].get("name"),
                                    "response": p["function_response"].get("response", {}),
                                }
                    except Exception:
                        pass

        yield {"type": "done"}
