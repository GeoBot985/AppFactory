from typing import TypedDict, Optional, List

class ChatRequestPayload(TypedDict):
    user_message: str
    selected_model: str
    rag_enabled: bool
    retrieval_query: Optional[str]
    retrieval_chunks: List[str]
    final_prompt: str

class WatcherResult(TypedDict):
    allowed: bool
    modified: bool
    payload: ChatRequestPayload
    watcher_notes: List[str]
    watcher_error: Optional[str]

def inspect_chat_request(payload: ChatRequestPayload) -> WatcherResult:
    """
    Accepts a structured chat request payload and returns a pass-through WatcherResult.
    If it fails internally, it fails open (passes the payload through).
    """
    try:
        # Pass-through behavior
        return {
            "allowed": True,
            "modified": False,
            "payload": payload,
            "watcher_notes": ["pass_through"],
            "watcher_error": None
        }
    except Exception as e:
        # Internal watcher failure, fail open
        return {
            "allowed": True,
            "modified": False,
            "payload": payload,
            "watcher_notes": ["watcher_failed_open"],
            "watcher_error": str(e)
        }
