from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class RiskAssessment(BaseModel):
    severity_level: Optional[str] = None
    risk_score: Optional[float] = None


class TaskInput(BaseModel):
    task_id: str
    task_type: str
    timestamp: Optional[str] = None

    username: Optional[str] = None
    user_email: Optional[str] = None
    requester_role: Optional[str] = None

    task_description: Optional[str] = None
    issue_summary: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    organization: Optional[str] = None
    location: Optional[str] = None

    entities: Dict[str, Any] = Field(default_factory=dict)
    questions_raised: List[str] = Field(default_factory=list)
    people_involved: List[Dict[str, Any]] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    source: Dict[str, Any] = Field(default_factory=dict)

    requested_action: Optional[str] = None
    policy_document_ids: List[int] = Field(default_factory=list)
    policy_type: Optional[str] = None

    risk_assessment: RiskAssessment = Field(default_factory=RiskAssessment)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DevPolicyUploadResponse(BaseModel):
    document_id: int
    file_name: str
    status: str


class PolicyProcessResponse(BaseModel):
    document_id: int
    file_name: str
    chunks_created: int
    rules_created: int
    status: str


class GovernanceDecisionOutput(BaseModel):
    task_id: str
    decision: str
    reason: str
    confidence: float
    requires_approval: bool
    next_agent: str
    matched_rule_ids: List[int]
    matched_chunk_ids: List[int]