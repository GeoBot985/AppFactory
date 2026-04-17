from __future__ import annotations
from datetime import datetime
from typing import Literal, List, Dict, Optional
from pydantic import BaseModel, Field
import uuid

KnowledgeOutcome = Literal["resolved", "not_resolved", "partial"]

class KnowledgeEntry(BaseModel):
    entry_id: str = Field(default_factory=lambda: f"kb_{uuid.uuid4().hex[:8]}")
    signature_id: str
    root_cause_id: str
    suggestion_id: str
    outcome: KnowledgeOutcome
    usage_count: int = 1
    success_count: int = 0
    last_used: datetime = Field(default_factory=datetime.now)

class SolutionCandidate(BaseModel):
    suggestion_id: str
    success_rate: float
    usage_count: int
    deterministic_rank: int

class PatternSolution(BaseModel):
    signature_id: str
    root_cause_id: str
    ranked_solutions: List[SolutionCandidate] = Field(default_factory=list)

class KnowledgeBaseData(BaseModel):
    entries: List[KnowledgeEntry] = Field(default_factory=list)
    mappings: Dict[str, PatternSolution] = Field(default_factory=dict)
