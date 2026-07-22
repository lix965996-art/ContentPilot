from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

Hashtag = Annotated[str, Field(min_length=1, max_length=40, pattern=r"^#?[^#\s][^#]*#?$")]


class WeiboGenerationOutput(BaseModel):
    title: str = Field(min_length=1, max_length=60)
    content: str = Field(min_length=10, max_length=2000)
    hashtags: list[Hashtag] = Field(default_factory=list, max_length=5)
    warnings: list[str] = Field(default_factory=list, max_length=10)


class XiaohongshuGenerationOutput(BaseModel):
    title: str = Field(min_length=1, max_length=30)
    content: str = Field(min_length=20, max_length=5000)
    hashtags: list[Hashtag] = Field(default_factory=list, max_length=10)
    cover_text: str = Field(default="", max_length=30)
    warnings: list[str] = Field(default_factory=list, max_length=10)


class WechatGenerationOutput(BaseModel):
    title: str = Field(min_length=1, max_length=64)
    summary: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=30, max_length=30_000)
    author: str = Field(default="", max_length=32)
    hashtags: list[Hashtag] = Field(default_factory=list, max_length=8)
    cover_prompt: str = Field(default="", max_length=200)
    warnings: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("content")
    @classmethod
    def require_markdown_structure(cls, value: str) -> str:
        if "\n" not in value:
            raise ValueError("微信公众号正文必须包含 Markdown 段落")
        return value


class QualityReviewOutput(BaseModel):
    factual_consistency: float = Field(ge=0, le=100)
    information_completeness: float = Field(ge=0, le=100)
    platform_fit: float = Field(ge=0, le=100)
    readability: float = Field(ge=0, le=100)
    format_compliance: float = Field(ge=0, le=100)
    issues: list[str] = Field(default_factory=list, max_length=20)
    suggestions: list[str] = Field(default_factory=list, max_length=20)


class ContentBriefOutput(BaseModel):
    core_thesis: str = Field(min_length=1, max_length=300)
    immutable_facts: list[str] = Field(min_length=1, max_length=15)
    supporting_points: list[str] = Field(default_factory=list, max_length=15)
    audience_needs: list[str] = Field(default_factory=list, max_length=10)
    content_gaps: list[str] = Field(default_factory=list, max_length=10)
    forbidden_inferences: list[str] = Field(default_factory=list, max_length=10)


class CreativeStrategyOutput(BaseModel):
    angle: str = Field(min_length=1, max_length=160)
    hook: str = Field(min_length=1, max_length=160)
    reader_value: str = Field(min_length=1, max_length=200)
    structure: list[str] = Field(min_length=2, max_length=10)
    cta: str = Field(default="", max_length=160)


class DeepReviewOutput(BaseModel):
    selected_candidate: int = Field(ge=0, le=1)
    factual_consistency: float = Field(ge=0, le=100)
    information_completeness: float = Field(ge=0, le=100)
    platform_fit: float = Field(ge=0, le=100)
    readability: float = Field(ge=0, le=100)
    format_compliance: float = Field(ge=0, le=100)
    non_genericness: float = Field(ge=0, le=100)
    issues: list[str] = Field(default_factory=list, max_length=12)
    improvements: list[str] = Field(default_factory=list, max_length=12)


class WeiboDeepDraftOutput(BaseModel):
    strategy: CreativeStrategyOutput
    candidates: list[WeiboGenerationOutput] = Field(min_length=2, max_length=2)


class XiaohongshuDeepDraftOutput(BaseModel):
    strategy: CreativeStrategyOutput
    candidates: list[XiaohongshuGenerationOutput] = Field(min_length=2, max_length=2)


class WechatDeepDraftOutput(BaseModel):
    strategy: CreativeStrategyOutput
    candidates: list[WechatGenerationOutput] = Field(min_length=2, max_length=2)


class WeiboDeepFinalOutput(DeepReviewOutput):
    final: WeiboGenerationOutput


class XiaohongshuDeepFinalOutput(DeepReviewOutput):
    final: XiaohongshuGenerationOutput


class WechatDeepFinalOutput(DeepReviewOutput):
    final: WechatGenerationOutput


class KeywordOutput(BaseModel):
    zh: str = Field(min_length=1, max_length=20)
    en: str = Field(min_length=1, max_length=50)
    reason: str = Field(min_length=1, max_length=100)


class KeywordExtractionOutput(BaseModel):
    keywords: list[KeywordOutput] = Field(min_length=1, max_length=8)


GenerationOutput = WeiboGenerationOutput | XiaohongshuGenerationOutput | WechatGenerationOutput
PlatformName = Literal["WEIBO", "XIAOHONGSHU", "WECHAT_OFFICIAL"]

OUTPUT_MODELS: dict[str, type[BaseModel]] = {
    "WEIBO": WeiboGenerationOutput,
    "XIAOHONGSHU": XiaohongshuGenerationOutput,
    "WECHAT_OFFICIAL": WechatGenerationOutput,
}

DEEP_DRAFT_MODELS: dict[str, type[BaseModel]] = {
    "WEIBO": WeiboDeepDraftOutput,
    "XIAOHONGSHU": XiaohongshuDeepDraftOutput,
    "WECHAT_OFFICIAL": WechatDeepDraftOutput,
}

DEEP_FINAL_MODELS: dict[str, type[BaseModel]] = {
    "WEIBO": WeiboDeepFinalOutput,
    "XIAOHONGSHU": XiaohongshuDeepFinalOutput,
    "WECHAT_OFFICIAL": WechatDeepFinalOutput,
}
