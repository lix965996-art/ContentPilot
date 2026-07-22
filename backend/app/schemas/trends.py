from pydantic import BaseModel, Field, HttpUrl


class TrendAnalyzeRequest(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    summary: str = Field(default="", max_length=3000)
    source: str = Field(min_length=2, max_length=50)
    url: HttpUrl


class TrendAngleOutput(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    audience: str = Field(min_length=2, max_length=120)
    hook: str = Field(min_length=2, max_length=180)
    outline: list[str] = Field(min_length=2, max_length=8)
    creative_goal: str = Field(min_length=2, max_length=80)


class TrendAnalysisOutput(BaseModel):
    relevance_reason: str = Field(min_length=2, max_length=300)
    recommended_angle_index: int = Field(ge=0, le=2)
    angles: list[TrendAngleOutput] = Field(min_length=2, max_length=3)
    risk_notes: list[str] = Field(default_factory=list, max_length=10)
    verification_questions: list[str] = Field(default_factory=list, max_length=10)
