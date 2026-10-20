from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.platform_content import validate_platform_publish

Hashtag = Annotated[str, Field(min_length=1, max_length=40, pattern=r"^#?[^#\s][^#]*#?$")]


class WeiboGenerationOutput(BaseModel):
    title: str = Field(min_length=1, max_length=60)
    content: str = Field(min_length=10, max_length=2000)
    hashtags: list[Hashtag] = Field(default_factory=list, max_length=5)
    warnings: list[str] = Field(default_factory=list, max_length=10)


class XGenerationOutput(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=280)
    hashtags: list[Hashtag] = Field(default_factory=list, max_length=4)
    warnings: list[str] = Field(default_factory=list, max_length=10)


class BlueskyGenerationOutput(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=3000)
    hashtags: list[Hashtag] = Field(default_factory=list, max_length=4)
    warnings: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def require_publishable_text(self) -> "BlueskyGenerationOutput":
        errors = validate_platform_publish(
            platform="BLUESKY",
            title=self.title,
            content=self.content,
            hashtags=self.hashtags,
            images=[],
        )
        if errors:
            raise ValueError("；".join(errors))
        return self


class MastodonGenerationOutput(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=10_000)
    hashtags: list[Hashtag] = Field(default_factory=list, max_length=4)
    warnings: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def require_publishable_text(self) -> "MastodonGenerationOutput":
        errors = validate_platform_publish(
            platform="MASTODON",
            title=self.title,
            content=self.content,
            hashtags=self.hashtags,
            images=[],
        )
        if errors:
            raise ValueError("；".join(errors))
        return self


class XiaohongshuGenerationOutput(BaseModel):
    title: str = Field(min_length=1, max_length=20)
    content: str = Field(min_length=20, max_length=1000)
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
            raise ValueError("微信公众号正文必须包含结构化段落")
        return value


class ToutiaoGenerationOutput(BaseModel):
    title: str = Field(min_length=2, max_length=30)
    summary: str = Field(min_length=20, max_length=120)
    content: str = Field(min_length=50, max_length=30_000)
    hashtags: list[Hashtag] = Field(default_factory=list, max_length=8)
    cover_prompt: str = Field(default="", max_length=200)
    warnings: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("content")
    @classmethod
    def require_paragraphs(cls, value: str) -> str:
        if "\n" not in value:
            raise ValueError("今日头条正文必须包含多个段落")
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


class XDeepDraftOutput(BaseModel):
    strategy: CreativeStrategyOutput
    candidates: list[XGenerationOutput] = Field(min_length=2, max_length=2)


class BlueskyDeepDraftOutput(BaseModel):
    strategy: CreativeStrategyOutput
    candidates: list[BlueskyGenerationOutput] = Field(min_length=2, max_length=2)


class MastodonDeepDraftOutput(BaseModel):
    strategy: CreativeStrategyOutput
    candidates: list[MastodonGenerationOutput] = Field(min_length=2, max_length=2)


class XiaohongshuDeepDraftOutput(BaseModel):
    strategy: CreativeStrategyOutput
    candidates: list[XiaohongshuGenerationOutput] = Field(min_length=2, max_length=2)


class WechatDeepDraftOutput(BaseModel):
    strategy: CreativeStrategyOutput
    candidates: list[WechatGenerationOutput] = Field(min_length=2, max_length=2)


class ToutiaoDeepDraftOutput(BaseModel):
    strategy: CreativeStrategyOutput
    candidates: list[ToutiaoGenerationOutput] = Field(min_length=2, max_length=2)


class WeiboDeepFinalOutput(DeepReviewOutput):
    final: WeiboGenerationOutput


class XDeepFinalOutput(DeepReviewOutput):
    final: XGenerationOutput


class BlueskyDeepFinalOutput(DeepReviewOutput):
    final: BlueskyGenerationOutput


class MastodonDeepFinalOutput(DeepReviewOutput):
    final: MastodonGenerationOutput


class XiaohongshuDeepFinalOutput(DeepReviewOutput):
    final: XiaohongshuGenerationOutput


class WechatDeepFinalOutput(DeepReviewOutput):
    final: WechatGenerationOutput


class ToutiaoDeepFinalOutput(DeepReviewOutput):
    final: ToutiaoGenerationOutput


class KeywordOutput(BaseModel):
    zh: str = Field(min_length=1, max_length=20)
    en: str = Field(min_length=1, max_length=50)
    reason: str = Field(min_length=1, max_length=100)


class KeywordExtractionOutput(BaseModel):
    keywords: list[KeywordOutput] = Field(min_length=1, max_length=8)


GenerationOutput = (
    WeiboGenerationOutput
    | XGenerationOutput
    | BlueskyGenerationOutput
    | MastodonGenerationOutput
    | XiaohongshuGenerationOutput
    | WechatGenerationOutput
    | ToutiaoGenerationOutput
)
PlatformName = Literal[
    "WEIBO", "X", "BLUESKY", "MASTODON", "XIAOHONGSHU", "WECHAT_OFFICIAL", "TOUTIAO"
]

OUTPUT_MODELS: dict[str, type[BaseModel]] = {
    "WEIBO": WeiboGenerationOutput,
    "X": XGenerationOutput,
    "BLUESKY": BlueskyGenerationOutput,
    "MASTODON": MastodonGenerationOutput,
    "XIAOHONGSHU": XiaohongshuGenerationOutput,
    "WECHAT_OFFICIAL": WechatGenerationOutput,
    "TOUTIAO": ToutiaoGenerationOutput,
}

DEEP_DRAFT_MODELS: dict[str, type[BaseModel]] = {
    "WEIBO": WeiboDeepDraftOutput,
    "X": XDeepDraftOutput,
    "BLUESKY": BlueskyDeepDraftOutput,
    "MASTODON": MastodonDeepDraftOutput,
    "XIAOHONGSHU": XiaohongshuDeepDraftOutput,
    "WECHAT_OFFICIAL": WechatDeepDraftOutput,
    "TOUTIAO": ToutiaoDeepDraftOutput,
}

DEEP_FINAL_MODELS: dict[str, type[BaseModel]] = {
    "WEIBO": WeiboDeepFinalOutput,
    "X": XDeepFinalOutput,
    "BLUESKY": BlueskyDeepFinalOutput,
    "MASTODON": MastodonDeepFinalOutput,
    "XIAOHONGSHU": XiaohongshuDeepFinalOutput,
    "WECHAT_OFFICIAL": WechatDeepFinalOutput,
    "TOUTIAO": ToutiaoDeepFinalOutput,
}
