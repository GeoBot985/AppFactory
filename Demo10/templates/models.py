from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum

class TemplateParameterType(Enum):
    STRING = "string"
    BOOLEAN = "boolean"
    ENUM = "enum"
    PATH = "path"

@dataclass
class TemplateParameter:
    name: str
    type: TemplateParameterType
    description: str
    required: bool = True
    default: Any = None
    choices: List[Any] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type.value,
            "description": self.description,
            "required": self.required,
            "default": self.default,
            "choices": self.choices
        }

@dataclass
class DraftTemplate:
    template_id: str
    version: int
    title: str
    description: str
    supported_task_kinds: List[str]
    parameters: List[TemplateParameter]
    skeleton: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "template_id": self.template_id,
            "version": self.version,
            "title": self.title,
            "description": self.description,
            "supported_task_kinds": self.supported_task_kinds,
            "parameters": [p.to_dict() for p in self.parameters],
            "skeleton": self.skeleton
        }

@dataclass
class TemplateFill:
    template_id: str
    version: int
    parameters: Dict[str, Any]
    filled_spec: Dict[str, Any]
    origin_type: str = "template"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "template_id": self.template_id,
            "version": self.version,
            "parameters": self.parameters,
            "filled_spec": self.filled_spec,
            "origin_type": self.origin_type
        }

class MatchStrength(Enum):
    EXACT = "exact"
    STRONG = "strong"
    WEAK = "weak"
    NONE = "none"

@dataclass
class TemplateSelectionResult:
    template_id: Optional[str]
    strength: MatchStrength
    reason: str
    inferred_parameters: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "template_id": self.template_id,
            "strength": self.strength.value,
            "reason": self.reason,
            "inferred_parameters": self.inferred_parameters
        }
