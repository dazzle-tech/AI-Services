"""Unit tests for conflict resolver."""

import pytest
from src.services.discharge_qa.conflict_resolver import ConflictResolver
from src.domain.entities import OnsiteDoc


def test_resolve_conflicts_no_conflict():
    """Test conflict resolution when values match."""
    resolver = ConflictResolver()
    
    report_value = "MI"
    source_values = [
        {"value": "MI", "doc_id": "DOC-001", "timestamp": "2024-01-15T10:00:00Z"}
    ]
    
    conflict = resolver.resolve_conflicts(report_value, source_values, [])
    
    assert conflict is None


def test_resolve_conflicts_with_conflict():
    """Test conflict resolution when values differ."""
    resolver = ConflictResolver()
    
    report_value = "MI"
    source_values = [
        {"value": "CHF", "doc_id": "DOC-001", "timestamp": "2024-01-15T10:00:00Z"}
    ]
    
    conflict = resolver.resolve_conflicts(report_value, source_values, [])
    
    assert conflict is not None
    assert conflict["report_value"] == "MI"
    assert conflict["source_value"] == "CHF"


def test_get_most_recent_doc():
    """Test getting most recent document."""
    resolver = ConflictResolver()
    
    docs = [
        OnsiteDoc(
            doc_id="DOC-001",
            doc_type="progress_note",
            timestamp="2024-01-15T10:00:00Z",
            department="Cardiology",
            content="Note 1"
        ),
        OnsiteDoc(
            doc_id="DOC-002",
            doc_type="progress_note",
            timestamp="2024-01-16T10:00:00Z",
            department="Cardiology",
            content="Note 2"
        )
    ]
    
    most_recent = resolver.get_most_recent_doc(docs)
    
    assert most_recent is not None
    assert most_recent.doc_id == "DOC-002"

