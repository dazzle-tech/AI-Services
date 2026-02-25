"""Pydantic schemas for MedAI Assistant."""
from typing import Optional, Dict, Any, List, Union
from enum import Enum
from pydantic import BaseModel, Field


# Chat Request/Response
class ChatRequest(BaseModel):
    """Chat request model."""
    message: str
    session_id: str = Field(default="session_default")
    user_id: str = Field(default="default_user")
    role: Optional[str] = None
    approved: bool = Field(default=False)


class ChatResponse(BaseModel):
    """Chat response model."""
    intent: str
    text: str
    data_json: Optional[Dict[str, Any]] = None
    original: Optional[str] = None
    corrected: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


# Patient Details
class PatientDetailsRequest(BaseModel):
    """Patient details request model."""
    patient_id: Union[int, str]  # Can be integer ID or string key (e.g., 'pat001')
    user_id: str = Field(default="default_user")
    role: Optional[str] = None
    session_id: Optional[str] = None


class PatientDetailsResponse(BaseModel):
    """Patient details response model."""
    ok: bool
    patient: Optional[Dict[str, Any]] = None
    message: Optional[str] = None


# SQL Generator
class SQLGeneratorRequest(BaseModel):
    """SQL generator request model."""
    user_id: str
    text: str


class SQLGeneratorResponse(BaseModel):
    """SQL generator response model."""
    user_id: str
    input_text: str
    sql_query: str


# Validator
class ValidatorRequest(BaseModel):
    """Validator request model."""
    user_id: str
    sql_query: str


class ValidatorResponse(BaseModel):
    """Validator response model."""
    user_id: str
    sql_query: str
    validation_result: Dict[str, Any]


# Formatter
class ColumnMeta(BaseModel):
    """Column metadata model."""
    name: str
    dtype: Optional[str] = None


class OutputType(str, Enum):
    """Output type enumeration."""
    SUMMARY = "summary"
    TABLE = "table"
    LIST = "list"
    CHART = "chart"


class KeyFigure(BaseModel):
    """Key figure model."""
    label: str
    value: Optional[Union[str, int, float, bool]] = None


class OutputJSON(BaseModel):
    """Output JSON structure."""
    type: OutputType
    count: int
    key_figures: List[KeyFigure] = Field(default_factory=list)
    highlights: List[str] = Field(default_factory=list)
    caveats: List[str] = Field(default_factory=list)
    table: Optional[List[Dict[str, Any]]] = None
    columns: Optional[List[str]] = None  # ordered column names for UI rendering


class FormatterRequest(BaseModel):
    """Formatter request model."""
    user_intent: str
    result_rows: List[Dict[str, Any]] = Field(default_factory=list)
    column_meta: Optional[List[ColumnMeta]] = None
    role: Optional[str] = "user"


class FormatterResponse(BaseModel):
    """Formatter response model."""
    summary: str
    json: OutputJSON  # This will be serialized as "json" in the response
    
    class Config:
        populate_by_name = True


# Admin Audit
class AdminHistoryResponse(BaseModel):
    """Admin history response model."""
    ok: bool
    count: int
    rows: List[Dict[str, Any]]


class AdminEventResponse(BaseModel):
    """Admin event response model."""
    ok: bool
    data: Dict[str, Any]


class AdminSearchResponse(BaseModel):
    """Admin search response model."""
    ok: bool
    count: int
    rows: List[Dict[str, Any]]

