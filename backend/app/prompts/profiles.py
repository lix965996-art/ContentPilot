from dataclasses import dataclass

from app.models.business import ContentArticle

PROMPT_VERSION = "2.0.0"

SYSTEM_PROMPT = (
    "你是资深中文内容编辑。只依据用户提供的原文改写，"
    "不补造数字、人物、经历、因果或结论。\n"
    "必须输出单个 JSON 对象，不得输出代码块或解释。"
    "信息不足时将风险写入 warnings，不得猜测。"
)


@dataclass(frozen=True)
class PlatformPromptProfile:
    name: str
    objective: str
    format_rules: tuple[str, ...]
    output_schema: str

    def render(self) -> str:
        rules = "\n".join(f"- {rule}" for rule in self.format_rules)
        return (
            f"目标平台：{self.name}\n平台目标：{self.objective}\n格式规则：\n{rules}"
            f"\n输出 JSON Schema 示例：\n{self.output_schema}"
        )


PLATFORM_PROFILES = {
    "WEIBO": PlatformPromptProfile(
        name="微博",
        objective="用高信息密度的短内容快速传递核心观点，并鼓励理性讨论。",
        format_rules=(
            "标题最多 60 字；正文建议 120～600 字，首句直接给出核心信息",
            "使用短段落，不编造热门话题、数据或亲身经历",
            "标签放入 hashtags 数组，最多 5 个；关闭标签时必须返回空数组",
            "Emoji 应克制，关闭 Emoji 时正文与标题不得出现 Emoji",
        ),
        output_schema=('{"title":"...","content":"...","hashtags":["#话题#"],"warnings":["..."]}'),
    ),
    "XIAOHONGSHU": PlatformPromptProfile(
        name="小红书",
        objective="以自然、有层次、便于收藏的笔记表达原文信息，不伪造体验。",
        format_rules=(
            "标题最多 30 字，正文使用短段落或清单，避免营销夸张和绝对化承诺",
            "不得把原文第三方信息改写成作者亲身体验",
            "标签放入 hashtags 数组，最多 10 个；关闭标签时必须返回空数组",
            "cover_text 是可选封面短句，最多 30 字",
            "关闭 Emoji 时标题、正文和封面短句不得出现 Emoji",
        ),
        output_schema=(
            '{"title":"...","content":"...","hashtags":["#标签"],'
            '"cover_text":"...","warnings":["..."]}'
        ),
    ),
    "WECHAT_OFFICIAL": PlatformPromptProfile(
        name="微信公众号",
        objective="形成可直接进入公众号编辑器的完整长文，结构清晰且忠于原文。",
        format_rules=(
            "标题最多 64 字，摘要最多 120 字",
            "content 必须为 Markdown，包含导语、二级标题、正文段落和结语",
            "不要输出不安全 HTML；不要编造引用、数据和案例",
            "hashtags 仅作为后台关键词；关闭标签时必须返回空数组",
            "cover_prompt 用于配图检索，不得包含品牌侵权或虚构人物",
        ),
        output_schema=(
            '{"title":"...","summary":"...","content":"## 小标题\\n\\n正文",'
            '"author":"","hashtags":[],"cover_prompt":"...","warnings":["..."]}'
        ),
    ),
}

LENGTH_GUIDANCE = {
    "SHORT": "精简：保留最关键事实，目标为该平台常规长度的下限",
    "MEDIUM": "标准：覆盖主要事实与必要背景，保持适中篇幅",
    "LONG": "详细：尽量覆盖原文的重要论点、条件与背景，但不得重复灌水",
}


def build_generation_prompt(
    article: ContentArticle,
    platform: str,
    options: dict,
) -> str:
    profile = PLATFORM_PROFILES[platform]
    audience = options.get("target_audience") or article.target_audience or "普通中文读者"
    style = options.get("style", "专业自然")
    length = options.get("length", "MEDIUM")
    preserve_meaning = options.get("preserve_meaning", 90)
    emoji_instruction = "允许适量使用" if options.get("include_emoji", True) else "禁止使用"
    hashtag_instruction = (
        "按平台规则生成"
        if options.get("include_hashtags", True)
        else "禁止生成，hashtags 必须为空数组"
    )
    return f"""{profile.render()}

用户改写参数（必须逐项执行）：
- style（表达风格）：{style}
- length（内容长度）：{length}；{LENGTH_GUIDANCE[length]}
- preserve_meaning（原意保留程度）：{preserve_meaning}/100
  分值越高越不得改变事实顺序、限定条件与结论
- target_audience（目标受众）：{audience}
- emoji（是否使用 Emoji）：{emoji_instruction}
- hashtags（是否生成标签）：{hashtag_instruction}

原文标题：{article.title}
原文摘要：{article.summary or "未提供"}
原文主题：{article.topic or "未提供"}
原文正文：
{article.source_text}

请严格返回符合平台 Schema 的 JSON。"""


QUALITY_REVIEW_PROMPT = (
    "你是内容质量审核员。对照原文和平台改写结果进行语义评审。\n"
    "分别给出 0～100 分：factual_consistency、information_completeness、"
    "platform_fit、readability、format_compliance。\n"
    "事实一致性关注是否虚构或改变限定条件；"
    "信息完整度关注核心事实是否遗漏；必须返回 JSON。"
)

KEYWORD_PROMPT = """从文章中提取 3～8 个适合图片检索的核心关键词。优先实体、场景和主题词，
为每项给出中文 zh、自然英文检索词 en 和简短 reason。只返回 {"keywords":[...]} JSON。"""
