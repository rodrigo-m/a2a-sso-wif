#!/usr/bin/env python3
import sys
import os
from dotenv import load_dotenv
import vertexai
from vertexai.preview import reasoning_engines

load_dotenv()

def get_display_name(agent_dir: str) -> str:
    return " ".join(word.capitalize() for word in agent_dir.split("_"))

def main():
    if len(sys.argv) < 2:
        print("Usage: python get_agent_id.py [--get-display-name | --get-id | --get-resource-name] <agent_dir>", file=sys.stderr)
        sys.exit(1)
        
    project = os.environ.get("PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        try:
            import subprocess
            project = subprocess.check_output(
                ["gcloud", "config", "get-value", "project"],
                stderr=subprocess.DEVNULL
            ).decode("utf-8").strip()
        except Exception:
            project = None
    region = os.environ.get("LOCATION") or os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    
    if sys.argv[1] == "--get-display-name":
        agent_dir = sys.argv[2] if len(sys.argv) > 2 else "a2a_agent"
        print(get_display_name(agent_dir))
        sys.exit(0)
        
    elif sys.argv[1] == "--get-id":
        agent_dir = sys.argv[2] if len(sys.argv) > 2 else "a2a_agent"
        display_name = get_display_name(agent_dir)
        try:
            vertexai.init(project=project, location=region)
            for engine in reasoning_engines.ReasoningEngine.list():
                if engine.display_name == display_name:
                    print(engine.resource_name.split("/")[-1])
                    sys.exit(0)
            sys.exit(0)
        except Exception as e:
            print(f"Error querying Vertex AI: {e}", file=sys.stderr)
            sys.exit(1)

    elif sys.argv[1] == "--get-resource-name":
        agent_dir = sys.argv[2] if len(sys.argv) > 2 else "a2a_agent"
        display_name = get_display_name(agent_dir)
        try:
            vertexai.init(project=project, location=region)
            for engine in reasoning_engines.ReasoningEngine.list():
                if engine.display_name == display_name:
                    print(engine.resource_name)
                    sys.exit(0)
            sys.exit(0)
        except Exception as e:
            print(f"Error querying Vertex AI: {e}", file=sys.stderr)
            sys.exit(1)
            
    else:
        agent_dir = sys.argv[1]
        display_name = get_display_name(agent_dir)
        try:
            vertexai.init(project=project, location=region)
            for engine in reasoning_engines.ReasoningEngine.list():
                if engine.display_name == display_name:
                    print(engine.resource_name.split("/")[-1])
                    sys.exit(0)
            sys.exit(0)
        except Exception as e:
            print(f"Error querying Vertex AI: {e}", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main()
