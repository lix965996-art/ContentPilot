import re

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


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

    @model_validator(mode="before")
    @classmethod
    def normalize_provider_fields(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        title = str(data.get("title") or "热点内容观察")
        data.setdefault(
            "audience",
            data.get("target_audience")
            or data.get("reader")
            or data.get("audience_profile")
            or "关注该热点的内容读者",
        )
        data.setdefault(
            "hook",
            data.get("angle") or data.get("core_value") or data.get("description") or title,
        )
        data.setdefault(
            "outline",
            data.get("key_points")
            or data.get("content_points")
            or [f"核验“{title}”的原始来源", "梳理已核验信息并形成平台观点"],
        )
        data.setdefault(
            "creative_goal",
            data.get("goal") or data.get("objective") or data.get("purpose") or "审慎分享热点信息",
        )
        return data

    @field_validator("outline", mode="before")
    @classmethod
    def normalize_numbered_outline(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        text = value.strip()
        parts = re.split(r"\s*(?=\d+[\.、）)]\s*)|[\n；;]+", text)
        normalized = [
            re.sub(r"^\d+[\.、）)]\s*", "", part).strip() for part in parts if part.strip()
        ]
        return normalized


class TrendAnalysisOutput(BaseModel):
    relevance_reason: str = Field(min_length=2, max_length=300)
    recommended_angle_index: int = Field(ge=0, le=2)
    angles: list[TrendAngleOutput] = Field(min_length=2, max_length=3)
    risk_notes: list[str] = Field(default_factory=list, max_length=10)
    verification_questions: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("risk_notes", "verification_questions", mode="before")
    @classmethod
    def normalize_list_text(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in re.split(r"[\n；;]+", value) if item.strip()]
        return value
