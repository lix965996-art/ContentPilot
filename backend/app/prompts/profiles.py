import json
from dataclasses import dataclass

from app.models.business import ContentArticle

PROMPT_VERSION = "4.0.0"

SYSTEM_PROMPT = (
    "你是资深中文内容编辑，擅长深度改写而非简单缩写。\n"
    "改写原则：\n"
    "1. 忠于原文事实，不补造数字、人物、经历、因果或结论；\n"
    "2. 深度不等于字数多，而是有观点层次：核心事实→分析解读→延伸思考→读者价值；\n"
    "3. 信息增量：改写必须提供比原文摘要更丰富的视角或更清晰的表达，而非简单缩写原文；\n"
    "4. 叙事节奏：开头用具体事实或场景切入，中间有逻辑推进，结尾有收束或延伸；\n"
    "5. 避免模板化：不要使用\u201c值得一提的是\u201d\u201c不可忽视\u201d\u201c引发广泛关注\u201d等套话。\n\n"
    "格式要求：\n"
    "- title、content、summary、cover_text 等用户可见文本中严禁出现井号字符；\n"
    "- 井号只允许存在于 hashtags 数组。\n"
    "- 必须输出单个 JSON 对象，不得输出代码块或解释。\n"
    "- 信息不足时将风险写入 warnings，不得猜测。"
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
            "title 是发布正文的首句钩子而非独立大标题；为兼容带图发布，"
            "title、content 和 hashtags 合并后的可见文本必须不超过 140 字",
            "即使用户选择详细长度，也要在 140 字内优先保留核心事实和必要限定条件",
            "使用短段落，不编造热门话题、数据或亲身经历",
            "标签放入 hashtags 数组，最多 5 个；关闭标签时必须返回空数组",
            "Emoji 应克制，关闭 Emoji 时正文与标题不得出现 Emoji",
            "正文使用纯文本，不要输出 **加粗**、* 列表等 Markdown 标记",
        ),
        output_schema=('{"title":"...","content":"...","hashtags":["#话题#"],"warnings":["..."]}'),
    ),
    "X": PlatformPromptProfile(
        name="X",
        objective="用简洁、自然、适合公开讨论的短帖传递核心事实和观点。",
        format_rules=(
            "title 是帖子的首句钩子，不是独立文章标题；title、content 和 hashtags "
            "合并后必须符合 X 的 280 加权字符限制",
            "中文、日文、韩文和大多数 Emoji 通常按 2 个加权字符计算；"
            "URL 按平台转换后的固定长度计算，因此必须保守控制篇幅",
            "优先使用短段落和清楚的观点，不编造数据、来源、经历或热门趋势",
            "hashtags 放入 hashtags 数组，最多 4 个；关闭标签时必须返回空数组",
            "正文使用纯文本，不输出 Markdown 标题、加粗标记或列表符号",
            "关闭 Emoji 时 title 和 content 不得出现 Emoji",
        ),
        output_schema=('{"title":"...","content":"...","hashtags":["#Topic"],"warnings":["..."]}'),
    ),
    "XIAOHONGSHU": PlatformPromptProfile(
        name="小红书",
        objective="以自然、有层次、便于收藏的笔记表达原文信息，不伪造体验。",
        format_rules=(
            "标题最多 20 字，正文最多 1000 字，使用短段落或清单，避免营销夸张和绝对化承诺",
            "不得把原文第三方信息改写成作者亲身体验",
            "标签放入 hashtags 数组，最多 10 个；关闭标签时必须返回空数组",
            "cover_text 是可选封面短句，最多 30 字",
            "关闭 Emoji 时标题、正文和封面短句不得出现 Emoji",
            "正文使用纯文本，不要输出 **加粗**、* 列表等 Markdown 标记",
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
            "content 必须为可排版的结构化文本，包含导语、小标题、正文段落和结语；"
            "系统会转换为公众号富文本 HTML",
            "不要输出不安全 HTML；不要编造引用、数据和案例",
            "hashtags 仅作为后台关键词；关闭标签时必须返回空数组",
            "cover_prompt 用于配图检索，不得包含品牌侵权或虚构人物",
            "小标题使用“一、标题”“二、标题”等中文序号，严禁使用井号或任何 Markdown 标题标记",
        ),
        output_schema=(
            '{"title":"...","summary":"...","content":"一、小标题\\n\\n正文",'
            '"author":"","hashtags":[],"cover_prompt":"...","warnings":["..."]}'
        ),
    ),
    "TOUTIAO": PlatformPromptProfile(
        name="今日头条",
        objective="形成适合头条号信息流阅读的完整文章，以明确标题、事实密度和清晰结构吸引阅读。",
        format_rules=(
            "标题为 2～30 个字符，准确具体，不使用标题党、虚假悬念或未经原文支持的结论",
            "正文使用短段落和清晰小标题，适合移动端阅读；重要事实、限定条件和来源语境不得遗漏",
            "正文使用纯文本，不输出井号标题、星号加粗、代码块或 HTML；系统会转换为安全富文本",
            "summary 为 40～120 字摘要，不得引入正文之外的新事实",
            "hashtags 仅作为后台关键词，最多 8 个；关闭标签时必须返回空数组",
            "cover_prompt 用于封面配图检索或生成，不得包含侵权品牌、虚构人物或误导性画面",
            "关闭 Emoji 时标题、摘要和正文不得出现 Emoji；即使允许，也只可克制使用",
        ),
        output_schema=(
            '{"title":"...","summary":"...","content":"一、标题\\n\\n正文",'
            '"hashtags":["#关键词"],"cover_prompt":"...","warnings":["..."]}'
        ),
    ),
}

LENGTH_GUIDANCE = {
    "SHORT": "精简：保留最关键事实，目标为该平台常规长度的下限",
    "MEDIUM": "标准：覆盖主要事实与必要背景，保持适中篇幅",
    "LONG": "详细：尽量覆盖原文的重要论点、条件与背景，但不得重复灌水",
}


FEW_SHOT_EXAMPLES: dict[str, str] = {
    "WEIBO": """
---
质量参照（微博）：
✗ 差稿示例：
  title: "人工智能引发关注"
  content: "近日，AI技术持续发展引发广泛关注。专家表示，人工智能将在多个领域发挥重要作用，值得关注。#人工智能#"
  问题：标题空洞无具体信息；"引发广泛关注"是套话；没有具体事实或数据；结尾敷衍。

✓ 好稿示例（假设原文是关于某城市用AI优化交通信号灯的新闻）：
  title: "杭州把AI装进红绿灯后，晚高峰缩短了18分钟"
  content: "杭州在127个路口部署了AI信号灯系统，通过实时车流数据动态调整配时。试运行3个月，晚高峰平均通行时间从42分钟降至24分钟。不过该系统在雨天场景下的准确率仍有待验证。#杭州AI交通#"
  好在哪：标题有具体城市和具体数据；开头直入事实；有具体数字支撑；包含了限定条件（雨天准确率）。
""",
    "X": """
---
质量参照（X）：
✗ 差稿示例：
  title: "New AI study shows promising results"
  content: "Researchers have published new findings about AI. The study shows AI can help in many areas. This is an important development. #AI #Research"
  问题：没有具体说哪个研究、什么结果；"many areas"是废话；没有信息增量。

✓ 好稿示例：
  title: "A 200-hospital AI trial just cut sepsis deaths by 30%"
  content: "Johns Hopkins deployed an early-warning model across 200 US hospitals. It analyzes vitals every 5 min and flags deterioration 6 hours before clinical signs. Mortality from sepsis dropped 30% in the first year. Key caveat: the model was trained on mostly urban hospitals—rural outcomes may differ."
  好在哪：标题有具体数字和机构；每句都有新信息；包含了关键限定条件。
""",
    "XIAOHONGSHU": """
---
质量参照（小红书）：
✗ 差稿示例：
  title: "AI学习工具推荐"
  content: "现在AI工具越来越多，今天给大家整理几个好用的AI学习工具，帮助大家提升学习效率。第一个是XXX，非常好用。第二个是YYY，功能强大。大家快去试试吧！"
  问题：标题无吸引力；"非常好用""功能强大"是空洞评价；没有具体使用场景和体验细节；像广告。

✓ 好稿示例（假设原文是关于AI辅助背单词的研究）：
  title: "用AI背单词，我3个月的实验数据"
  content: "去年9月开始用间隔重复+AI语境生成来背GRE词汇，记录了一下：
传统方式 vs AI辅助，3个月后的测试正确率差距很大。
核心区别不是速度，而是AI会根据你的错误模式调整复习频率。
但有个坑：AI生成的例句有时会偏离真实考试语境，需要手动筛选。
适合人群：备考周期>2个月、每天能投入30分钟以上的人。"
  好在哪：标题有具体场景；有实验数据感；优缺点都有；给出了适用条件。
""",
    "WECHAT_OFFICIAL": """
---
质量参照（微信公众号）：
✗ 差稿示例：
  title: "人工智能的发展趋势与未来展望"
  content: "一、引言\n\n随着人工智能技术的快速发展，各行各业都在积极拥抱AI变革。本文将为您梳理AI领域的最新动态。\n\n二、AI发展现状\n\n近年来，AI技术取得了长足进步，在医疗、教育、金融等领域发挥了重要作用。专家表示，AI将成为未来发展的关键驱动力。\n\n三、未来展望\n\n不可忽视，AI发展仍面临诸多挑战。让我们拭目以待，共同见证AI的辉煌未来。"
  问题：标题模板化；引言是废话；"长足进步""重要作用""关键驱动力"全是空话；结尾套话；全文没有具体事实。

✓ 好稿示例：
  title: "当AI开始读CT片：三甲医院三年的真实数据"
  content: "一、12万张CT片背后的实验\n\n2021年起，协和医院放射科引入了AI辅助诊断系统。三年间，系统累计处理了12万张胸部CT，覆盖了肺结节、纵隔肿瘤等7类常见病变。\n\n二、准确率97%的背后\n\nAI在肺结节检测上的敏感率达到97.2%，比该院放射科医生的平均水平高出4.3个百分点。但值得注意的是，假阳性率也达到了15%——这意味着每100个健康人中，会有15人被误判为疑似患者。\n\n三、医生没有被替代，但工作方式变了\n\n系统上线后，放射科医生的阅片速度提升了60%，但诊断结论的最终决定权仍在医生手中。一个显著变化是：年轻医生借助AI系统，诊断准确率提升幅度最大，达到了8.7个百分点。"
  好在哪：标题有具体场景；每个段落有具体数据；包含限定条件和nuance；逻辑递进。
""",
    "TOUTIAO": """
---
质量参照（今日头条）：
✗ 差稿示例：
  title: "AI教育引发热议"
  content: "近日，AI在教育领域的应用引发了广泛讨论。有专家认为，AI将改变传统教育模式，为学生提供更加个性化的学习体验。同时也有学者指出，AI教育仍面临诸多挑战，需要谨慎推进。"
  问题：标题无信息量；"引发广泛讨论"是万能套话；没有具体案例或数据；正反两面都说了但都是空话。

✓ 好稿示例：
  title: "北京5所中学用AI教数学，一学期后成绩差拉大了"
  content: "2023年秋季，北京海淀区5所中学在初二年级引入了AI自适应数学教学系统。系统会根据学生的答题情况实时调整题目难度和知识点讲解方式。\n\n一学期的数据出来了：使用AI系统的班级，数学平均分提高了8.3分，但标准差也增大了12分——意味着好的更好了，差的更差了。\n\n研究人员发现，自律性强的学生能充分利用系统的个性化推荐，而自律性弱的学生反而更容易在AI"陪伴"下走神。"
  好在哪：标题有具体地点、具体结果；数据具体；有因果分析；有nuance（不是简单的好坏判断）。
""",
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
- visible_text（可见文本）：title、content、summary、cover_text 中严禁出现井号字符；
  井号仅允许存在于 hashtags 数组

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

CONTENT_BRIEF_PROMPT = """你是严谨的内容研究编辑。只依据原文生成创作简报，不得引入外部事实。

请完成以下分析：
1. 核心论点：原文最想传达的一个核心信息是什么？
2. 论证链条：原文用哪些关键事实支撑这个论点？按逻辑顺序排列。
3. 不可改变的事实：数据、人名、机构名、时间、地点等硬性事实，必须原样保留。
4. 限定条件：原文中的"可能""在一定条件下""据某来源"等限定，不得省略或强化。
5. 受众认知缺口：目标读者在阅读本文前可能不知道什么？读后应该获得什么新认知？
6. 可延伸方向：原文信息中可以进一步解读或关联的角度（但不得编造）。
7. 原文信息缺口：哪些关键信息缺失会影响读者理解？
8. 严禁推断：哪些结论是原文没有明确说的，改写时绝不能暗示。

信息缺失就明确列入 content_gaps，绝不能补造。必须只返回符合指定结构的 JSON。"""


def build_deep_draft_prompt(
    article: ContentArticle, platform: str, options: dict, brief: dict
) -> str:
    return f"""{build_generation_prompt(article, platform, options)}

本次为深度创作模式，不是简单缩写原文，而是要进行有信息增量的改写。

创作目标：{options.get("creative_goal", "知识分享")}。
用户额外创作要求：{options.get("creative_requirements") or "未提供"}。

已核验的原文创作简报：
{brief}

---
一、制定创作策略（strategy）

1. angle（切入角度）——必须从以下类型中选择一个最适合本文的角度，不得泛泛而谈：
   - 反直觉切入：揭示与常识相反的事实或结论
   - 人物/故事线：以具体人物或事件经过为叙事主线
   - 数据驱动：以关键数据为切入点，用数据讲故事
   - 场景代入：以读者可感知的具体场景开头，引出主题
   - 对比视角：通过时间对比、中外对比、前后对比制造张力
   - 问题解答：以读者最可能提出的疑问为线索展开
   选择角度后说明为什么这个角度最适合本文和目标受众。

2. hook（开头钩子）——必须是具体的，不得使用以下无效模式：
   ✗ "近日，……引发广泛关注" ✗ "众所周知" ✗ "随着……的发展"
   ✓ 一个反常识的具体事实 ✓ 一个有画面感的场景 ✓ 一个直击痛点的问题 ✓ 一个令人意外的数据

3. reader_value（读者价值）——用一句话说清：读者读完这篇能获得什么？
   不能是"了解更多"这种废话，必须是具体的认知收获。

4. structure（内容结构）——给出 3～6 个逻辑递进的段落要点，每个要点说明该段要传递什么信息。
   结构必须有推进感：不能是并列罗列，要有从"是什么→为什么→意味着什么→怎么办"的层次。

5. cta（行动引导）——符合平台习惯，自然不突兀。

二、生成 2 个候选稿（candidates）

两个候选必须明显不同，至少在一个维度上有本质差异：
- 不同的切入角度（如一个用数据驱动，一个用人物故事线）
- 或不同的叙事结构（如一个按时间线，一个按重要性递进）
- 或不同的目标侧重（如一个偏专业深度，一个偏大众可读性）

质量底线：
- 开头 2 句内必须出现具体信息，不得用空洞背景铺垫
- 每个段落必须有至少一个具体事实或数据支撑
- 结尾不得用"让我们拭目以待""值得关注"等套话收束
- 全文不得出现"值得一提的是""不可忽视""引发广泛关注"等模板化表达

两个候选都必须遵守原文事实和用户参数。

{FEW_SHOT_EXAMPLES.get(platform, "")}

返回 JSON：{{"strategy":{{...}},"candidates":[平台稿件1,平台稿件2]}}。"""


DEEP_REVIEW_PROMPT = """你是内容主编和事实审核员。你的任务是从两个候选稿中选出更好的一个，指出问题并实际修正为 final 版本。

评审流程：
1. 逐项对照创作简报中的 immutable_facts 和 forbidden_inferences，检查两个候选是否有事实偏差或越界推断。
2. 按以下 6 个维度分别打分（0～100）：
   - 事实一致性：是否有虚构数据、篡改限定条件、颠倒因果？简报中禁止推断的内容是否被暗示？
   - 信息完整度：核心论点和关键事实是否遗漏？简报中的论证链条是否完整呈现？
   - 平台适配度：格式、长度、语气是否符合目标平台？
   - 可读性：开头是否有吸引力？段落间是否有逻辑推进？是否有冗长或空洞的段落？
   - 格式合规性：字段格式是否符合平台 Schema？
   - 非模板化程度：是否使用了"值得一提的是""不可忽视""引发广泛关注"等套话？开头是否用"近日""随着"等无效模式？结尾是否用"让我们拭目以待"等敷衍收束？
3. 选择更好的候选（selected_candidate: 0 或 1）。
4. 对选中的候选进行实际修正，输出为 final。修正时：
   - 删除或降级简报未支持的事实
   - 替换模板化表达为具体内容
   - 确保开头 2 句内出现具体信息
   - 确保每个段落有具体事实或数据支撑
   - 确保结尾有实质性收束而非套话

final 的标题、正文、摘要和封面短句中严禁出现井号字符；井号只允许存在于 hashtags 数组。
必须只返回符合指定结构的 JSON。"""


COHERENCE_REVIEW_PROMPT = """你是长文终审编辑，负责文章发布前的最后一次润色。
你的工作不是重写文章，而是修补段落间的衔接裂缝，让读者阅读时不会感到突兀或断裂。

评审维度（各 0～100 分）：
1. 过渡自然度：段落之间是否有逻辑桥梁？是否出现"突然跳到另一个话题"的情况？
2. 论证推进感：全文是否有从"是什么→为什么→意味着什么→怎么办"的递进？还是并列罗列？
3. 开头力度：前 2 句是否直入具体信息？是否有"近日""随着""众所周知"等无效开头？
4. 收束质量：结尾是否呼应开头或给出实质性总结？是否用了"让我们拭目以待""值得关注"等套话？

修正规则：
- 只修补过渡句、衔接词和段落首尾句
- 不新增事实或数据，不删除已有内容
- 不改变文章整体结构
- 替换所有模板化表达为具体内容
- 确保修正后仍符合平台格式要求

必须只返回符合指定结构的 JSON。"""


def build_coherence_review_prompt(
    article: ContentArticle,
    platform: str,
    final_draft: dict,
    brief: dict,
) -> str:
    platform_name = PLATFORM_PROFILES[platform].name
    return f"""目标平台：{platform_name}
原文标题：{article.title}
原文正文：
{article.source_text}

创作简报中的论证链条：
{json.dumps(brief.get("supporting_points", []), ensure_ascii=False, indent=2)}

当前终稿：
{json.dumps(final_draft, ensure_ascii=False, indent=2)}

---
请按终审流程逐项检查上述终稿，找出衔接问题并直接修正。
修正后的完整稿件必须包含所有字段，格式符合平台 Schema。"""
