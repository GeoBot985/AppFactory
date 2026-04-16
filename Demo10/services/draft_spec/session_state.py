from __future__ import annotations
import hashlib
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from .models import DraftSpec

@dataclass
class TranslationAttempt:
    index: int
    source_request_hash: str
    source_request_summary: str
    success: bool
    uncertainty_count: int
    generated_draft_id: str
    timestamp: str

class DraftSpecSessionState:
    def __init__(self):
        self.current_request: str = ""
        self.current_draft: Optional[DraftSpec] = None
        self.draft_status: str = "empty" # empty, translated, edited, invalid, valid_draft_pending_compile
        self.translation_ledger: List[TranslationAttempt] = []

    def record_attempt(self, request_text: str, draft: Optional[DraftSpec], success: bool):
        request_hash = hashlib.sha256(request_text.encode()).hexdigest()[:12]
        attempt = TranslationAttempt(
            index=len(self.translation_ledger) + 1,
            source_request_hash=request_hash,
            source_request_summary=request_text[:50],
            success=success,
            uncertainty_count=len(draft.uncertainties) if draft else 0,
            generated_draft_id=draft.draft_id if draft else "none",
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
        )
        self.translation_ledger.append(attempt)

    def reset(self):
        self.current_request = ""
        self.current_draft = None
        self.draft_status = "empty"
        # We might keep the ledger for audit
