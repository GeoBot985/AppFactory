from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

class ChatRequest(BaseModel):
    model: str
    message: str
    mode: str = "chat" # chat, document, personal
    document_ids: Optional[List[str]] = None
    chat_document_id: Optional[str] = None

class ChatResponse(BaseModel):
    reply: str
    evidence: Optional[List[Dict[str, Any]]] = None
    debug: Dict[str, Any]

class WatcherEvent(BaseModel):
    stage: str
    timestamp: str
    decision: str
    notes: str
    selected_model: str
    user_message_preview: str

class TurnContext(BaseModel):
    model: str
    user_message: str
    session_id: str = "default_session"
    request_started_at: str
    watcher_events: List[WatcherEvent] = Field(default_factory=list)
    ollama_request_summary: Optional[Dict[str, Any]] = None
    ollama_response_summary: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
