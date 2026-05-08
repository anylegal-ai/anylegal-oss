"""
Pydantic models for the Document Editor module.

Defines data structures for clause analysis, redline suggestions,
playbook management, and API request/response schemas.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime
from enum import Enum

class ClauseType(str, Enum):
    """Common contract clause types."""
    INDEMNIFICATION = "indemnification"
    LIMITATION_OF_LIABILITY = "limitation_of_liability"
    TERMINATION = "termination"
    CONFIDENTIALITY = "confidentiality"
    WARRANTY = "warranty"
    REPRESENTATIONS = "representations"
    GOVERNING_LAW = "governing_law"
    DISPUTE_RESOLUTION = "dispute_resolution"
    FORCE_MAJEURE = "force_majeure"
    ASSIGNMENT = "assignment"
    ENTIRE_AGREEMENT = "entire_agreement"
    AMENDMENT = "amendment"
    NOTICE = "notice"
    SEVERABILITY = "severability"
    OTHER = "other"

class Position(str, Enum):
    """Clause position/favorability."""
    CLIENT_FAVORABLE = "client_favorable"
    BALANCED = "balanced"
    COUNTERPARTY_FAVORABLE = "counterparty_favorable"

class RiskLevel(str, Enum):
    """Risk assessment levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class Severity(str, Enum):
    """Suggestion priority/severity."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class RuleType(str, Enum):
    """Types of playbook rules."""
    AUTO_ACCEPT = "auto_accept"
    ALWAYS_FLAG = "always_flag"
    SUGGEST_ALTERNATIVE = "suggest_alternative"
    REJECT = "reject"

class RepresentingParty(str, Enum):
    """Party being represented."""
    BUYER = "buyer"
    SELLER = "seller"
    LANDLORD = "landlord"
    TENANT = "tenant"
    EMPLOYER = "employer"
    EMPLOYEE = "employee"
    LICENSOR = "licensor"
    LICENSEE = "licensee"
    SERVICE_PROVIDER = "service_provider"
    CLIENT = "client"

class ClauseAnalysis(BaseModel):
    """Result of analyzing a clause."""
    clause_type: str
    position: str                                    
    risk_level: str                               
    issues: List[str] = []
    summary: str
    confidence: float = Field(default=0.8, ge=0, le=1)

class RedlineSuggestion(BaseModel):
    """A suggested change to the document."""
    original: str
    suggested: str
    explanation: str
    priority: str = "medium"                     
    source: str = "llm"                                       
    source_id: Optional[int] = None
    applied: bool = False

class AnalyzeRequest(BaseModel):
    """Request to analyze a clause."""
    text: str = Field(..., min_length=10, description="Clause text to analyze")
    context: Optional[str] = Field(default="", description="Surrounding context")
    representing: str = Field(default="buyer", description="Party being represented")
    document_type: Optional[str] = Field(default=None, description="Contract type (NDA, SPA, etc.)")
    jurisdiction: str = Field(default="GENERAL", description="Jurisdiction code")

class RedlineRequest(BaseModel):
    """Request to generate redlines for a clause."""
    text: str = Field(..., min_length=10, description="Clause text to redline")
    context: Optional[str] = Field(default="", description="Surrounding context")
    representing: str = Field(default="buyer", description="Party being represented")
    document_type: Optional[str] = Field(default=None, description="Contract type")
    jurisdiction: str = Field(default="GENERAL", description="Jurisdiction code")
    apply_playbook: bool = Field(default=True, description="Apply playbook rules")
    playbook_strictness: str = Field(default="balanced", description="strict, balanced, or flexible")

class RedlineResponse(BaseModel):
    """Response with redline suggestions."""
    analysis: ClauseAnalysis
    suggestions: List[RedlineSuggestion]
    playbook_matches: List[dict] = []
    tokens_used: Optional[dict] = None

class AnalyzeResponse(BaseModel):
    """Response from clause analysis."""
    analysis: ClauseAnalysis
    suggestions: List[RedlineSuggestion] = []

class PlaybookClause(BaseModel):
    """A clause in the playbook library."""
    id: Optional[int] = None
    user_id: Optional[int] = None
    clause_type: str
    position: str                                                      
    title: str
    clause_text: str
    explanation: Optional[str] = None
    jurisdiction: str = "GENERAL"
    contract_type: Optional[str] = None
    tags: List[str] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    usage_count: int = 0

class PlaybookClauseCreate(BaseModel):
    """Request to create a playbook clause."""
    clause_type: str
    position: str
    title: str
    clause_text: str
    explanation: Optional[str] = None
    jurisdiction: str = "GENERAL"
    contract_type: Optional[str] = None
    tags: List[str] = []

class PlaybookRule(BaseModel):
    """A rule for automatic redlining."""
    id: Optional[int] = None
    user_id: Optional[int] = None
    name: str
    description: Optional[str] = None
    rule_type: str                                                         
    trigger_clause_type: Optional[str] = None
    trigger_keywords: List[str] = []
    trigger_semantic: Optional[str] = None
    action: dict                                    
    severity: str = "medium"
    priority: int = 0
    is_active: bool = True
    created_at: Optional[datetime] = None

class PlaybookRuleCreate(BaseModel):
    """Request to create a playbook rule."""
    name: str
    description: Optional[str] = None
    rule_type: str
    trigger_clause_type: Optional[str] = None
    trigger_keywords: List[str] = []
    trigger_semantic: Optional[str] = None
    action: dict
    severity: str = "medium"
    priority: int = 0

class TriageClassification(str, Enum):
    """NDA triage classification levels."""
    STANDARD_APPROVAL = "STANDARD_APPROVAL"
    COUNSEL_REVIEW = "COUNSEL_REVIEW"
    FULL_REVIEW = "FULL_REVIEW"

class TriageFinding(BaseModel):
    """A finding from the NDA triage analysis."""
    criterion: str
    status: Literal["pass", "flag", "fail"]
    detail: str

class TriageRequest(BaseModel):
    """Request to triage an NDA."""
    document_text: str = Field(..., min_length=100, description="NDA document text")
    triage_context: Optional[str] = Field(default="", description="User-provided context")
    apply_playbook: bool = Field(default=True, description="Apply playbook rules")

class TriageResponse(BaseModel):
    """Response from NDA triage."""
    classification: str
    confidence: float = Field(ge=0, le=1)
    summary: str
    key_findings: List[TriageFinding]
    risk_factors: List[str]
    recommended_actions: List[str]
    playbook_deviations: List[str] = []
    tokens_used: Optional[dict] = None

class DocumentTemplate(BaseModel):
    """A document template stored by the user."""
    id: Optional[int] = None
    user_id: Optional[int] = None
    name: str
    description: Optional[str] = None
    template_type: str                                     
    content: str                         
    variables: List[str] = []                                                     
    jurisdiction: str = "GENERAL"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    usage_count: int = 0

class DocumentTemplateCreate(BaseModel):
    """Request to create a document template."""
    name: str
    description: Optional[str] = None
    template_type: str
    content: str
    variables: List[str] = []
    jurisdiction: str = "GENERAL"

class ContextTemplate(BaseModel):
    """A context preset for reviews (e.g., 'Buyer focused on IP', 'Seller conservative')."""
    id: Optional[int] = None
    user_id: Optional[int] = None
    name: str
    description: Optional[str] = None
    context_text: str                                             
    document_types: List[str] = []                                           
    is_default: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class ContextTemplateCreate(BaseModel):
    """Request to create a context template."""
    name: str
    description: Optional[str] = None
    context_text: str
    document_types: List[str] = []
    is_default: bool = False

class DocumentSession(BaseModel):
    """An editing session for a document."""
    id: str
    user_id: int
    document_name: str
    document_type: Optional[str] = None
    status: str = "active"                                
    created_at: datetime
    updated_at: datetime

class RedlineHistoryEntry(BaseModel):
    """A redline change in the session history."""
    id: int
    session_id: str
    change_type: str                                    
    original_text: Optional[str] = None
    new_text: Optional[str] = None
    clause_type: Optional[str] = None
    source: str                                              
    status: str = "pending"                               
    created_at: datetime

