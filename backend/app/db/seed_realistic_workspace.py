"""Repair and maintain the opt-in realistic local workspace demo data.

This script only updates records identified by the ``editorial-*`` media marker.
It never touches user-created articles. External publishing and engagement data is
explicitly labelled as simulated because no official platform API is involved.
"""

from __future__ import annotations

from html import escape

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.business import (
    AccountActivityStat,
    ContentArticle,
    ContentVariant,
    EngagementMetric,
    Experiment,
    ExperimentSample,
    MediaAsset,
    PlatformAccount,
    PlatformAuthLog,
    PublishLog,
    PublishRecommendation,
    PublishSchedule,
)
from app.models.user import User

ARTICLE_DATA = [
    {
        "title": "一篇内容，如何适配微博、小红书和公众号",
        "topic": "多平台内容运营",
        "audience": "需要同时运营多个内容平台的编辑与品牌团队",
        "tone": "专业、清晰、有行动建议",
        "keywords": ["多平台运营", "内容改写", "品牌表达", "发布流程"],
        "status": "APPROVED",
        "summary": "同一组事实需要按平台重新组织表达，而不是简单复制或截短。",
        "source": (
            "同一篇原稿发布到不同平台时，真正需要调整的不是事实，而是信息出现的顺序。"
            "微博适合先给结论，再用短句补充背景；小红书更强调具体场景、可扫描的段落和收藏价值；"
            "公众号则需要保留完整论证，让标题、导语、小标题和结尾形成连续阅读体验。\n\n"
            "团队可以先建立一份“事实母稿”，明确不能改动的数据、人物、时间和结论，再为每个平台"
            "生成独立版本。发布前检查标题、长度、话题、图片比例和行动引导，发布后把互动数据与"
            "人工修改记录带回复盘。这样做的价值不是多发三次，而是让一份可靠信息抵达三种阅读场景。"
        ),
    },
    {
        "title": "AI 辅助写作如何保留品牌原意",
        "topic": "AI 内容协作",
        "audience": "使用生成式 AI 的内容编辑、市场和品牌负责人",
        "tone": "克制、可信、重视事实",
        "keywords": ["AI 写作", "品牌一致性", "事实核验", "人工审核"],
        "status": "GENERATED",
        "summary": "把不可改动事实、表达边界和验证步骤写进流程，AI 才能成为可靠的协作者。",
        "source": (
            "AI 可以帮助整理结构、转换语气和生成初稿，但品牌原意不能只靠一句“请保持原意”来保护。"
            "在生成之前，应先标出不能改动的事实、数字、专有名词和结论，同时给出目标受众、语气、"
            "长度与禁用表达。\n\n"
            "生成之后需要两层检查：规则检查负责长度、格式、话题和敏感词，语义检查负责事实一致性、"
            "信息完整度与是否出现未经来源支持的新结论。最后保留生成稿和人工修改稿，记录修改比例。"
            "当团队能看见哪些地方总要人工重写，下一版提示词才有明确的优化方向。"
        ),
    },
    {
        "title": "内容日历不是排期表，而是团队协作地图",
        "topic": "内容日历",
        "audience": "内容团队负责人、编辑、设计和渠道运营",
        "tone": "务实、鼓励协作",
        "keywords": ["内容日历", "排期", "团队协作", "工作流"],
        "status": "APPROVED",
        "summary": "好用的内容日历同时呈现主题、负责人、版本、素材、审核节点和发布状态。",
        "source": (
            "只写发布日期的表格很难解决内容团队的协作问题。真正好用的内容日历，应该让编辑知道"
            "稿件处于哪个版本，让设计知道什么时候交图，让审核人看见截止时间，也让渠道运营提前"
            "确认账号和发布方式。\n\n"
            "建议每条内容至少记录主题、目标受众、负责人、平台版本、素材状态、审核节点、发布时间"
            "和最终链接。遇到延期时，不要只拖动日期，还要同步说明依赖项。每周复盘一次拥堵最严重"
            "的环节，日历就会从静态计划变成一张持续更新的协作地图。"
        ),
    },
    {
        "title": "公众号长文排版：让读者愿意多停留一分钟",
        "topic": "公众号排版",
        "audience": "微信公众号编辑和长内容创作者",
        "tone": "友好、具体、有示例感",
        "keywords": ["微信公众号", "长文排版", "可读性", "编辑技巧"],
        "status": "APPROVED",
        "summary": "排版的目标不是装饰页面，而是减少理解阻力并建立稳定的阅读节奏。",
        "source": (
            "公众号长文让人读不下去，往往不是内容太长，而是读者很难判断自己读到了哪里。清楚的"
            "导语、准确的小标题、适度留白和统一的强调方式，可以帮助读者快速建立文章地图。\n\n"
            "每个段落尽量只承担一个任务：解释背景、给出方法或提供证据。重要数字要与来源一起出现，"
            "图片前后补充必要说明，避免连续使用大段加粗和过多颜色。发布前在手机上完整预览一次，"
            "检查图片清晰度、段落断行、链接和文末行动引导。排版不是装饰，而是内容的一部分。"
        ),
    },
    {
        "title": "为内容选择配图：好看之外还要讲清信息",
        "topic": "内容配图",
        "audience": "社交媒体编辑、设计协作者和内容运营",
        "tone": "简洁、实用、重视版权",
        "keywords": ["内容配图", "视觉叙事", "图片版权", "无障碍文本"],
        "status": "GENERATED",
        "summary": "配图应服务信息表达，同时记录来源、授权范围和替代文本。",
        "source": (
            "一张漂亮但与主题无关的图片，可能会让读者对内容产生错误预期。选择配图时，可以依次"
            "检查三个问题：它是否补充了正文没有直接呈现的信息，是否符合平台的裁切比例，以及团队"
            "是否拥有清楚的使用授权。\n\n"
            "封面负责建立第一印象，正文图负责解释流程、展示细节或提供证据，两者不应混用。素材入库"
            "时记录来源、作者、搜索关键词和使用范围，并为图片填写简洁准确的替代文本。真正可靠的"
            "视觉工作流，不只追求好看，也能在几个月后回答这张图从哪里来、为什么用在这里。"
        ),
    },
]


def paragraph_html(text: str) -> str:
    return "".join(f"<p>{escape(part)}</p>" for part in text.split("\n\n"))


def emoji_count(text: str) -> int:
    return sum(
        1 for char in text if "\U0001f300" <= char <= "\U0001faff" or "\u2600" <= char <= "\u27bf"
    )


def platform_copy(article: dict[str, object], platform: str) -> tuple[str, str, list[str]]:
    title = str(article["title"])
    summary = str(article["summary"])
    topic = str(article["topic"])
    source = str(article["source"])
    if platform == "WEIBO":
        content = (
            f"{summary}\n\n"
            "我的做法是先锁定不可改动的事实，再根据阅读场景调整信息顺序。"
            "发布前检查标题、长度、图片和行动引导，发布后把互动与人工修改带回复盘。"
            "一份内容不该只是复制三次，而要在三个平台都说得自然、准确。"
        )
        return title, content, [f"#{topic}#", "#内容运营#"]
    if platform == "XIAOHONGSHU":
        content = (
            f"📌 最近整理内容工作流时，我重新复盘了这个问题：{title}\n\n"
            f"先说结论：{summary}\n\n"
            "我会按这 4 步处理：\n"
            "1️⃣ 锁定事实、数字和专有名词\n"
            "2️⃣ 明确读者与平台阅读场景\n"
            "3️⃣ 分平台重组标题和段落\n"
            "4️⃣ 发布前预览，发布后记录修改\n\n"
            "这套方法不追求一键生成，而是让每次修改都有依据，也方便团队继续复盘。"
        )
        return title[:20], content, [f"#{topic}", "#内容运营", "#工作方法"]
    content = (
        f"{summary}\n\n{source}\n\n"
        "落到日常执行，可以从一份小而完整的检查清单开始：先确认事实与目标读者，再完成平台版式、"
        "图片和链接检查，最后记录发布结果及人工修改。流程被持续记录之后，团队才能分辨问题来自"
        "选题、表达、审核还是发布时间，并据此优化下一轮内容。"
    )
    return title, content, [topic, "内容运营", "编辑方法"]


def update_variants(db, article: ContentArticle, data: dict[str, object]) -> None:
    variants = db.scalars(
        select(ContentVariant).where(ContentVariant.article_id == article.id)
    ).all()
    for variant in variants:
        if variant.review_status == "REJECTED":
            rejected = (
                "AI 写作很方便，大家直接用就可以了。它能自动保证所有信息正确，"
                "也不需要再安排人工审核。"
            )
            variant.title = "AI 写作可以完全替代人工审核吗"
            variant.content_text = rejected
            variant.content_html = paragraph_html(rejected)
            variant.hashtags_json = ["#AI写作#"]
            variant.emoji_count = 0
            variant.word_count = len(rejected)
            variant.model_name = "local-demo-editor"
            variant.prompt_version = "demo-old-v1"
            variant.generation_duration_ms = 0
            variant.token_usage = 0
            variant.prompt_tokens = 0
            variant.completion_tokens = 0
            variant.estimated_cost = 0
            variant.quality_score = 41
            variant.manual_edit_ratio = 0
            variant.review_detail_json = {
                "dataNotice": "本地演示评审记录",
                "factConsistency": 25,
                "informationCompleteness": 35,
                "platformFit": 58,
                "readability": 76,
                "formatCompliance": 62,
                "reason": "加入了原稿没有支持的绝对化结论，因此被拒绝。",
            }
            variant.original_generated_text = rejected
            continue

        variant_title, content, hashtags = platform_copy(data, variant.platform)
        variant.title = variant_title
        variant.content_text = content
        variant.content_html = paragraph_html(content)
        variant.hashtags_json = hashtags
        variant.emoji_count = emoji_count(content)
        variant.word_count = len(content.replace("\n", ""))
        variant.model_name = "local-demo-editor"
        variant.prompt_version = "demo-profile-v2"
        variant.generation_duration_ms = 0
        variant.token_usage = 0
        variant.prompt_tokens = 0
        variant.completion_tokens = 0
        variant.estimated_cost = 0
        article_index = ARTICLE_DATA.index(data)
        variant.quality_score = 88 + article_index
        variant.manual_edit_ratio = [0.08, 0.14, 0.05, 0.11, 0.07][article_index]
        variant.review_detail_json = {
            "dataNotice": "本地演示评审记录，不代表真实 LLM 调用",
            "factConsistency": 94,
            "informationCompleteness": 90,
            "platformFit": 91,
            "readability": 93,
            "formatCompliance": 96,
        }
        variant.original_generated_text = content


def update_workspace() -> dict[str, int]:
    db = SessionLocal()
    try:
        operator = db.scalar(select(User).where(User.username == "operator"))
        if operator is None:
            raise RuntimeError("operator demo user is missing")

        article_ids = sorted(
            set(
                db.scalars(
                    select(MediaAsset.article_id).where(
                        MediaAsset.source_id.like("editorial-%-cover")
                    )
                ).all()
            )
        )
        if len(article_ids) != len(ARTICLE_DATA):
            raise RuntimeError(
                f"expected {len(ARTICLE_DATA)} editorial demo articles, got {len(article_ids)}"
            )

        articles = db.scalars(
            select(ContentArticle)
            .where(ContentArticle.id.in_(article_ids))
            .order_by(ContentArticle.id)
        ).all()
        for article, data in zip(articles, ARTICLE_DATA, strict=True):
            article.title = str(data["title"])
            article.source_text = str(data["source"])
            article.summary = str(data["summary"])
            article.topic = str(data["topic"])
            article.target_audience = str(data["audience"])
            article.tone = str(data["tone"])
            article.keywords_json = list(data["keywords"])
            article.status = str(data["status"])
            update_variants(db, article, data)

            assets = db.scalars(select(MediaAsset).where(MediaAsset.article_id == article.id)).all()
            for asset in assets:
                kind = "封面图" if asset.usage_type == "COVER" else "正文配图"
                asset.source = "LOCAL_DEMO"
                asset.photographer_name = "ContentPilot 本地演示素材"
                asset.photographer_url = None
                asset.alt_text = f"{article.title}的{kind}"
                asset.search_keyword = str(data["topic"])

        generated_assets = [
            (0, "content-adaptation.webp", "COVER", "多平台内容适配与分发"),
            (0, "team-workflow.webp", "BODY", "内容团队协作流程"),
            (1, "ai-brand-meaning.webp", "COVER", "AI 写作与品牌原意保护"),
            (1, "content-experiment.webp", "BODY", "内容策略对照实验"),
            (2, "content-calendar.webp", "COVER", "内容日历与团队协作"),
            (2, "publishing-schedule.webp", "BODY", "内容发布排期与时段规划"),
            (3, "longform-reading.webp", "COVER", "长文章排版与阅读体验"),
            (4, "visual-selection.webp", "COVER", "内容配图选择与裁切"),
        ]
        for article_index, filename, usage_type, alt_text in generated_assets:
            article = articles[article_index]
            source_id = f"ai-generated:{filename}"
            asset = db.scalar(select(MediaAsset).where(MediaAsset.source_id == source_id))
            if asset is None:
                asset = MediaAsset(
                    article_id=article.id,
                    source="AI_GENERATED",
                    source_id=source_id,
                    image_url=f"/media/generated/{filename}",
                    thumbnail_url=f"/media/generated/{filename}",
                    photographer_name="ContentPilot AI",
                    photographer_url=None,
                    alt_text=alt_text,
                    search_keyword=str(ARTICLE_DATA[article_index]["topic"]),
                    usage_type=usage_type,
                    selected=True,
                )
                db.add(asset)
            else:
                asset.image_url = f"/media/generated/{filename}"
                asset.thumbnail_url = f"/media/generated/{filename}"
                asset.alt_text = alt_text
                asset.selected = True
            if usage_type == "COVER":
                db.query(MediaAsset).filter(
                    MediaAsset.article_id == article.id,
                    MediaAsset.usage_type == "COVER",
                    MediaAsset.source_id != source_id,
                ).update({"selected": False})

        account_names = {
            "WEIBO": "ContentPilot 微博（本地演示）",
            "WECHAT_OFFICIAL": "ContentPilot 公众号（草稿演示）",
            "XIAOHONGSHU": "ContentPilot 小红书（人工发布）",
        }
        accounts = db.scalars(
            select(PlatformAccount).where(PlatformAccount.user_id == operator.id)
        ).all()
        for account in accounts:
            account.account_name = account_names[account.platform]
            account.auth_type = "NONE"
            account.status = "CONNECTED"
            account.publish_mode = "MANUAL_CONFIRM" if account.platform == "XIAOHONGSHU" else "MOCK"
            account.capabilities_json = (
                ["MANUAL_PACKAGE", "COPY_TEXT", "DOWNLOAD_MEDIA"]
                if account.platform == "XIAOHONGSHU"
                else ["SIMULATED_PUBLISH", "LOCAL_WORKFLOW_ONLY"]
            )
            account.last_error = "本地演示账号：尚未配置官方平台凭证，不会向外部平台发送内容。"

            auth_logs = db.scalars(
                select(PlatformAuthLog).where(PlatformAuthLog.platform_account_id == account.id)
            ).all()
            for auth_log in auth_logs:
                auth_log.message = "本地演示账号已就绪；未连接官方平台接口。"
                auth_log.detail_json = {"dataSource": "SIMULATED", "credentials": False}

        schedules = db.scalars(
            select(PublishSchedule).where(PublishSchedule.article_id.in_(article_ids))
        ).all()
        for schedule in schedules:
            article = next(item for item in articles if item.id == schedule.article_id)
            is_complete = schedule.status != "PENDING"
            schedule.publish_package_json = {
                "title": article.title,
                "dataNotice": (
                    "本地模拟发布结果，未连接外部平台"
                    if is_complete
                    else "待发布演示排期，执行前需确认平台连接"
                ),
                "mediaCount": 2,
            }
            if is_complete:
                schedule.result_mode = "SIMULATED"
                schedule.published_url = (
                    f"https://example.invalid/contentpilot/{schedule.platform.lower()}/"
                    f"{schedule.id}"
                )
                schedule.external_id = f"simulated-{schedule.id}"
            else:
                schedule.result_mode = None
                schedule.published_url = None
                schedule.external_id = None

            logs = db.scalars(select(PublishLog).where(PublishLog.schedule_id == schedule.id)).all()
            for log in logs:
                log.request_summary = f"准备《{article.title}》的{schedule.platform}发布包"
                log.response_summary = (
                    "本地模拟流程执行完成，未调用外部平台接口。"
                    if is_complete
                    else "排期已保存，等待人工确认。"
                )
                log.error_message = None

            recommendations = db.scalars(
                select(PublishRecommendation).where(
                    PublishRecommendation.article_id == article.id,
                    PublishRecommendation.platform == schedule.platform,
                )
            ).all()
            for recommendation in recommendations:
                recommendation.reason_json = [
                    "参考本地演示账号的历史活跃时段",
                    "避开团队已安排的相邻内容",
                    "推荐结果仅用于演示，不代表真实平台流量预测",
                ]

        schedule_ids = [schedule.id for schedule in schedules]
        metrics = db.scalars(
            select(EngagementMetric).where(EngagementMetric.schedule_id.in_(schedule_ids))
        ).all()
        for metric in metrics:
            metric.engagement_total = (
                metric.likes + metric.comments + metric.collects + metric.shares
            )
            denominator = metric.impressions or metric.followers
            metric.engagement_rate = (
                round(metric.engagement_total / denominator, 6) if denominator else 0
            )

        account_ids = [account.id for account in accounts]
        activity_stats = db.scalars(
            select(AccountActivityStat).where(AccountActivityStat.account_id.in_(account_ids))
        ).all()
        for stat in activity_stats:
            # Account history uses a decimal fraction (0.054 means 5.4%).
            if stat.avg_engagement_rate > 1:
                stat.avg_engagement_rate = stat.avg_engagement_rate / 100

        experiment = db.scalar(
            select(Experiment).where(
                Experiment.created_by == operator.id,
                Experiment.status == "ACTIVE",
            )
        )
        if experiment:
            experiment.status = "RUNNING"
            experiment.name = "发布时间建议：推荐时段 vs 常规时段"
            experiment.hypothesis = (
                "在内容质量相近的前提下，推荐时段可能获得更高互动率；当前数据全部为本地模拟样本。"
            )
            experiment.control_description = "常规时段：团队固定排期时间"
            experiment.treatment_description = "推荐时段：参考本地账号活跃度评分"
            experiment.metrics_json = {
                "primary": "engagement_rate",
                "secondary": ["impressions", "collects"],
                "dataNotice": "SIMULATED",
            }
            experiment.result_json = {
                "status": "collecting",
                "dataNotice": "本地模拟数据，不可作为真实运营结论",
            }
            experiment.conclusion = "样本仍在收集中，暂不下结论。"
            samples = db.scalars(
                select(ExperimentSample).where(ExperimentSample.experiment_id == experiment.id)
            ).all()
            for index, sample in enumerate(samples, start=1):
                label = "推荐时段" if sample.group_type == "TREATMENT" else "常规时段"
                sample.sample_label = f"{label}模拟样本 {index}"
                value = dict(sample.metric_value_json or {})
                value["dataNotice"] = "SIMULATED"
                sample.metric_value_json = value

        db.commit()
        return {
            "articles": len(articles),
            "variants": sum(len(article.variants) for article in articles),
            "accounts": len(accounts),
            "schedules": len(schedules),
            "experiments": 1 if experiment else 0,
        }
    finally:
        db.close()


if __name__ == "__main__":
    print(update_workspace())
