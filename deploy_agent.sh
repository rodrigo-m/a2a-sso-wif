#!/bin/bash
# ==============================================================================
# Deploy / In-Place Update ADK Agent to Google Cloud Agent Runtime (Vertex AI)
# ==============================================================================

set -e

# Load environment variables from .env
if [ -f .env ]; then
  echo "Loading environment variables from .env..."
  export $(grep -v '^#' .env | xargs)
fi

AGENT_DIR="${1:-a2a_agent}"
PROJECT="${GOOGLE_CLOUD_PROJECT:-${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}}"
if [ -z "$PROJECT" ]; then
  echo "Error: GOOGLE_CLOUD_PROJECT or PROJECT_ID must be set in .env or via gcloud config."
  exit 1
fi
REGION="${GOOGLE_CLOUD_LOCATION:-${LOCATION:-${LLM_LOCATION:-us-central1}}}"

echo "=================================================================="
echo "Deploying ADK Agent to Agent Runtime (Vertex AI)"
echo "=================================================================="
echo "Agent Directory: $AGENT_DIR"
echo "Project ID:      $PROJECT"
echo "Region:          $REGION"

PYTHON_CMD=".venv/bin/python"
ADK_CMD=".venv/bin/adk"

if [ ! -f "$ADK_CMD" ]; then
  ADK_CMD="adk"
  PYTHON_CMD="python3"
fi

DISPLAY_NAME=$($PYTHON_CMD get_agent_id.py --get-display-name "$AGENT_DIR")
AGENT_ENGINE_ID=$($PYTHON_CMD get_agent_id.py --get-id "$AGENT_DIR")

if [ -n "$AGENT_ENGINE_ID" ]; then
  echo "Found existing deployed Agent Engine ID: $AGENT_ENGINE_ID ('$DISPLAY_NAME')"
  echo "Performing in-place update to Agent Runtime..."
  $ADK_CMD deploy agent_engine --project="$PROJECT" --region="$REGION" --display_name="$DISPLAY_NAME" --agent_engine_id="$AGENT_ENGINE_ID" "$AGENT_DIR"
else
  echo "No existing deployed agent found. Creating a new instance on Agent Runtime..."
  $ADK_CMD deploy agent_engine --project="$PROJECT" --region="$REGION" --display_name="$DISPLAY_NAME" "$AGENT_DIR"
fi

echo "=================================================================="
echo "Deployment / Update Completed Successfully!"
echo "=================================================================="
