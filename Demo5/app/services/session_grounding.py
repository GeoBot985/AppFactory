import datetime
import uuid
import tzlocal
from typing import TypedDict, Optional, List
from app.config import (
    DEFAULT_MODEL, DEFAULT_MODE, AGENT_PURPOSE, DEFAULT_LOCATION, DEFAULT_TIMEZONE
)
from ollama_client import get_models

class GroundingContext(TypedDict):
    session_id: str
    session_started_at: str
    current_datetime: str
    timezone: str
    location: str
    agent_purpose: str
    default_mode: str
    selected_model: str
    model_available: bool
    available_models: List[str]

# Global session context
_current_grounding: Optional[GroundingContext] = None

async def build_session_grounding(
    active_mode: str = DEFAULT_MODE,
    selected_model: str = DEFAULT_MODEL
) -> GroundingContext:
    global _current_grounding

    session_id = uuid.uuid4().hex
    start_time = datetime.datetime.now(datetime.timezone.utc)

    # Get local timezone
    try:
        local_tz = tzlocal.get_localzone_name()
    except Exception:
        local_tz = DEFAULT_TIMEZONE or "UTC"

    # Current local time
    local_now = datetime.datetime.now()

    # Check model availability
    available_models, _ = await get_models()
    model_available = selected_model in available_models

    grounding: GroundingContext = {
        "session_id": session_id,
        "session_started_at": start_time.isoformat(),
        "current_datetime": local_now.isoformat(),
        "timezone": local_tz,
        "location": DEFAULT_LOCATION,
        "agent_purpose": AGENT_PURPOSE,
        "default_mode": active_mode,
        "selected_model": selected_model,
        "model_available": model_available,
        "available_models": available_models
    }

    _current_grounding = grounding
    return grounding

def get_session_grounding() -> Optional[GroundingContext]:
    return _current_grounding

def format_grounding_for_debug(context: GroundingContext) -> str:
    if not context:
        return "No grounding context initialized."

    output = "Session Grounding\n"
    output += f"datetime: {context['current_datetime']}\n"
    output += f"timezone: {context['timezone']}\n"
    output += f"location: {context['location']}\n"
    output += f"purpose: {context['agent_purpose']}\n"
    output += f"default mode: {context['default_mode']}\n"
    output += f"model: {context['selected_model']}"

    if not context['model_available']:
        output += " (WARNING: Not available)"

    return output
