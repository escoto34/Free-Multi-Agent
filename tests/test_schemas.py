"""
Unit tests for checking positive (valid) and negative (invalid) schema validation
using Pydantic.
"""

import pytest
from pydantic import ValidationError

from schemas.vibe_coding import TechnicalSpec, CodeArtifact, DebugReport
from schemas.deep_research import SafetyClassification, CondensedTrends, GroundedReport


# ---------------------------------------------------------------------------
# Vibe Coding Schemas Validation Tests
# ---------------------------------------------------------------------------

def test_technical_spec_validation():
    # Positive
    valid_data = {
        "architecture": "MVC Architecture with REST controller.",
        "test_cases": ["Test API response status", "Test DB entry persistence"],
        "files_to_create": ["app/main.py", "tests/test_main.py"],
    }
    spec = TechnicalSpec(**valid_data)
    assert spec.architecture == "MVC Architecture with REST controller."
    assert len(spec.test_cases) == 2

    # Negative (missing required files_to_create field)
    invalid_data = {
        "architecture": "MVC Architecture",
        "test_cases": ["Test case"],
    }
    with pytest.raises(ValidationError):
        TechnicalSpec(**invalid_data)


def test_code_artifact_validation():
    # Positive
    valid_data = {
        "files": {
            "app/main.py": "print('hello')",
            "tests/test_main.py": "assert True"
        },
        "summary": "Implemented main app and tests.",
    }
    artifact = CodeArtifact(**valid_data)
    assert artifact.summary == "Implemented main app and tests."
    assert "app/main.py" in artifact.files

    # Negative (files is not a dict)
    invalid_data = {
        "files": ["not", "a", "dict"],
        "summary": "Hello",
    }
    with pytest.raises(ValidationError):
        CodeArtifact(**invalid_data)


def test_debug_report_validation():
    # Positive
    valid_data = {
        "passed": False,
        "issues": ["SyntaxError: invalid syntax in main.py line 4"],
        "suggested_fix": "Add missing closing parentheses on line 4.",
    }
    report = DebugReport(**valid_data)
    assert report.passed is False
    assert len(report.issues) == 1
    assert report.suggested_fix == "Add missing closing parentheses on line 4."

    # Negative (passed is missing)
    invalid_data = {
        "issues": ["No errors"],
    }
    with pytest.raises(ValidationError):
        DebugReport(**invalid_data)


# ---------------------------------------------------------------------------
# Deep Research Schemas Validation Tests
# ---------------------------------------------------------------------------

def test_safety_classification_validation():
    # Positive
    valid_data = {
        "is_safe": True,
        "reasons": [],
    }
    safety = SafetyClassification(**valid_data)
    assert safety.is_safe is True
    assert len(safety.reasons) == 0

    # Negative (is_safe is missing)
    invalid_data = {
        "reasons": ["Unsafe content detected"],
    }
    with pytest.raises(ValidationError):
        SafetyClassification(**invalid_data)


def test_condensed_trends_validation():
    # Positive
    valid_data = {
        "technologies": ["LangGraph", "PydanticAI"],
        "rationale": "Prioritized agentic workflow libraries as requested.",
    }
    trends = CondensedTrends(**valid_data)
    assert len(trends.technologies) == 2
    assert trends.rationale.startswith("Prioritized")

    # Negative (technologies is missing)
    invalid_data = {
        "rationale": "Missing technologies.",
    }
    with pytest.raises(ValidationError):
        CondensedTrends(**invalid_data)


def test_grounded_report_validation():
    # Positive
    valid_data = {
        "content": "This is a grounded report citing sources [1].",
        "sources": ["https://example.com/source-1"],
    }
    report = GroundedReport(**valid_data)
    assert report.content == "This is a grounded report citing sources [1]."
    assert len(report.sources) == 1

    # Negative (sources is missing)
    invalid_data = {
        "content": "No sources.",
    }
    with pytest.raises(ValidationError):
        GroundedReport(**invalid_data)
