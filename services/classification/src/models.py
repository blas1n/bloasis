"""Pydantic models for Classification Service.

These models are service-specific and used for internal business logic.
Inter-service communication uses Proto messages only (gRPC).
"""

from typing import List

from pydantic import BaseModel, Field


class SectorScore(BaseModel):
    """Individual sector score from Stage 1 analysis."""

    sector: str = Field(description="GICS sector name")
    score: float = Field(ge=0, le=100, description="Sector score (0-100)")
    rationale: str = Field(description="Rationale for score from FinGPT")
    selected: bool = Field(description="Whether sector is selected for Stage 2")


class ThemeScore(BaseModel):
    """Individual theme score from Stage 2 analysis."""

    theme: str = Field(description="Investment theme name")
    sector: str = Field(description="Sector this theme belongs to")
    score: float = Field(ge=0, le=100, description="Theme score (0-100)")
    rationale: str = Field(description="Rationale for score from FinGPT")
    representative_symbols: List[str] = Field(
        default_factory=list, description="Representative symbols for this theme"
    )


class CandidateSymbol(BaseModel):
    """Individual candidate symbol from Stage 1+2."""

    symbol: str = Field(description="Stock symbol")
    sector: str = Field(description="Sector classification")
    theme: str = Field(description="Primary investment theme")
    preliminary_score: float = Field(ge=0, le=100, description="Preliminary score from Stage 1+2")


class SectorAnalysisResult(BaseModel):
    """Complete sector analysis result (Stage 1)."""

    sectors: List[SectorScore] = Field(description="All sector scores")
    regime: str = Field(description="Market regime used for analysis")
    cached_at: str = Field(description="ISO 8601 timestamp of cache")


class ThematicAnalysisResult(BaseModel):
    """Complete thematic analysis result (Stage 2)."""

    themes: List[ThemeScore] = Field(description="All theme scores")
    cached_at: str = Field(description="ISO 8601 timestamp of cache")


class CandidateResult(BaseModel):
    """Complete candidate symbols result (Stage 1+2)."""

    candidates: List[CandidateSymbol] = Field(description="Candidate symbols")
    selected_sectors: List[str] = Field(description="Selected sectors from Stage 1")
    top_themes: List[str] = Field(description="Top themes from Stage 2")
    regime: str = Field(description="Market regime used for analysis")
