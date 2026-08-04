"""
Pydantic schemas for the System A (Vibe Coding) pipeline.
These models define the strict API boundaries between the Architect, Coder,
and Debugger agents.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class TechnicalSpec(BaseModel):
    """Output schema for the Architect agent.

    Defines the system design, components, file mapping, and unit test requirements.
    """

    architecture: str = Field(
        ...,
        description="Detailed description of the architectural design, patterns, and components."
    )
    test_cases: list[str] = Field(
        ...,
        description="A list of unit test descriptions or verification requirements that must pass."
    )
    files_to_create: list[str] = Field(
        ...,
        description="List of file paths that the programmer must create or modify."
    )


class CodeArtifact(BaseModel):
    """Output schema for the merged coordinator-implementer agent.

    WAVE-18: the architect role is folded into coder, so this schema now also
    carries the planning fields the old TechnicalSpec produced. Defaults keep
    existing callers working.
    """

    files: dict[str, str] = Field(
        ...,
        description="A dictionary mapping relative file paths to their full source code content."
    )
    summary: str = Field(
        ...,
        description="Summary of the changes made, explaining the layout and logic of the code."
    )
    files_to_create: list[str] = Field(
        default_factory=list,
        description="List of relative file paths that must be created or modified (surgical, minimal set).",
    )
    test_cases: list[str] = Field(
        default_factory=list,
        description="Critical test cases / content checks the implementation must satisfy.",
    )
    architecture: str = Field(
        default="",
        description="Short rationale for the architecture and any preservation requirements.",
    )


class DebugReport(BaseModel):
    """Output schema for the Debugger agent.

    Represents the result of running unit tests against the generated code.
    """

    passed: bool = Field(
        ...,
        description="True if all tests passed and no issues were found, False otherwise."
    )
    issues: list[str] = Field(
        default_factory=list,
        description="A list of error logs, syntax problems, or failed assertion descriptions."
    )
    suggested_fix: Optional[str] = Field(
        default=None,
        description="Detailed instructions or code snippet suggesting how the programmer should fix the issues."
    )
    fixed_files: Optional[dict[str, str]] = Field(
        default=None,
        description="Optional full corrected source for every file that must change. "
        "Use only when the fix is fully understood and the affected files are "
        "fully visible; otherwise leave None and use suggested_fix.",
    )
