"""Unit tests for scoring."""

import pytest
from src.services.discharge_qa.scoring import QAScorer


def test_calculate_score_no_errors():
    """Test score calculation with no errors."""
    scorer = QAScorer()
    
    score = scorer.calculate_score([], [], [])
    
    assert score == 100


def test_calculate_score_with_errors():
    """Test score calculation with errors."""
    scorer = QAScorer()
    
    errors = [
        {"severity": "critical"},
        {"severity": "high"}
    ]
    
    score = scorer.calculate_score(errors, [], [])
    
    assert score < 100
    assert score == 60  # 100 - 25 - 15


def test_calculate_score_critical_safety_cap():
    """Test that critical safety errors cap score at 50."""
    scorer = QAScorer()
    
    errors = [
        {"severity": "critical", "category": "safety"}
    ]
    
    score = scorer.calculate_score(errors, [], [])
    
    assert score <= 50


def test_generate_summary():
    """Test summary generation."""
    scorer = QAScorer()
    
    errors = [{"severity": "high"}]
    
    summary = scorer.generate_summary(85, errors, [], [])
    
    assert "85" in summary
    assert "error" in summary.lower()

