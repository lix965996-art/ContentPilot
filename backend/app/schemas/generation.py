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
