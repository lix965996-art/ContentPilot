import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.business import (
    ActivityPrior,
    ContentArticle,
    ContentVariant,
    EngagementMetric,
    Experiment,
    ExperimentSample,
    PlatformAccount,
    PublishSchedule,
    SystemSetting,
)
from app.models.user import Role, User

ROLE_DEFINITIONS = {
    "ADMIN": ("管理员", "用户、配置、日志和全局统计管理"),
    "OPERATOR": ("内容运营者", "内容生产、审核、排期和数据复盘"),
    "VIEWER": ("查看者", "只读访问内容、排期和报告"),
}

DEMO_USERS = (
    ("admin", "Admin@123456", "系统管理员", "admin@socialflow.local", "ADMIN"),
    ("operator", "Operator@123456", "内容运营者", "operator@socialflow.local", "OPERATOR"),
    ("viewer", "Viewer@123456", "数据查看者", "viewer@socialflow.local", "VIEWER"),
)


def seed_database(db: Session) -> None:
    roles: dict[str, Role] = {}
    for code, (name, description) in ROLE_DEFINITIONS.items():
        role = db.scalar(select(Role).where(Role.code == code))
        if role is None:
            role = Role(code=code, name=name, description=description)
            db.add(role)
            db.flush()
        roles[code] = role

    for username, password, display_name, email, role_code in DEMO_USERS:
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            user = User(
                username=username,
                password_hash=hash_password(password),
                display_name=display_name,
                email=email,
                status="ACTIVE",
            )
            db.add(user)
        if roles[role_code] not in user.roles:
            user.roles = [roles[role_code]]
    db.commit()
    seed_system_settings(db)
    if settings.app_demo_mode:
        seed_demo_business_data(db, roles)


def seed_system_settings(db: Session) -> None:
    """Create only runtime configuration; business records are never seeded by default."""
    setting_defs = [
        ("llm.provider", settings.llm_provider, False, "大模型提供方"),
        ("llm.base_url", settings.llm_base_url, False, "OpenAI 兼容接口地址"),
        ("llm.api_key", settings.llm_api_key, True, "大模型 API Key"),
        ("llm.model", settings.llm_model, False, "模型名称"),
        ("media.unsplash_key", settings.unsplash_access_key, True, "Unsplash Access Key"),
        ("publish.mode", settings.publish_mode, False, "默认发布方式"),
        ("app.timezone", settings.app_timezone, False, "系统时区"),
        ("logs.retention_days", "90", False, "日志保留天数"),
    ]
    for key, value, secret, description in setting_defs:
        if not db.scalar(select(SystemSetting).where(SystemSetting.setting_key == key)):
            db.add(
                SystemSetting(
                    setting_key=key,
                    setting_value=value,
                    is_secret=secret,
                    description=description,
                )
            )
    db.commit()


ARTICLE_SEEDS = [
    (
        "校园新媒体如何建立稳定的内容节奏",
        "校园新媒体团队常常面临选题分散、多人协作断层和发布时间不稳定的问题。建立统一选题池、明确审核节点，并用周度日历安排不同平台版本，可以让内容生产更有秩序。复盘时应记录发布时间、互动率和人工修改耗时，而不是只看点赞总数。",
        "校园运营",
    ),
    (
        "AI 辅助写作的三条事实边界",
        "AI 可以帮助提炼结构、转换表达和生成初稿，但不能替代事实核验。"
        "涉及人物、数字和研究结论时，应回到原始材料逐项确认。"
        "团队还应保留生成版本和人工修改记录，以便复盘效率与质量。",
        "人工智能",
    ),
    (
        "一次校园摄影展的幕后记录",
        "从征集作品到线下布展，校园摄影展经历了主题讨论、版权确认、作品筛选和空间规划。志愿者团队用两周时间完成一百余幅作品的信息核对，并为每位创作者保留完整署名。",
        "校园文化",
    ),
    (
        "数据复盘不是做一张漂亮图表",
        "有效的数据复盘需要从问题出发。先定义曝光、互动和转化口径，再比较不同平台、内容主题与发布时间。样本量不足时应明确限制，避免把相关性写成因果关系。",
        "数据分析",
    ),
    (
        "毕业季内容策划清单",
        "毕业季内容可以围绕人物故事、校园记忆、实用服务和仪式现场展开。策划时要提前确认肖像授权、采访时间和发布渠道，并为突发天气和现场变动准备替代方案。",
        "毕业季",
    ),
    (
        "社团招新如何减少信息差",
        "清晰的招新内容应说明社团做什么、成员能获得什么、需要投入多少时间，以及报名方式和截止日期。真实活动照片和成员经验比口号更能帮助新生判断是否适合。",
        "社团",
    ),
    (
        "一篇长文如何适配三个平台",
        "同一篇长文在微博需要快速给出观点，在小红书需要可扫描的段落和场景化标题，在公众号则要保留完整逻辑。适配不是简单截断，而是在事实一致的前提下重新组织信息。",
        "内容创作",
    ),
    (
        "校园活动直播的准备流程",
        "活动直播前应检查网络、收音、电源和备用设备，明确导播、摄影与主持分工。还要准备延迟开场、设备掉线等预案，并在结束后及时归档素材和授权记录。",
        "活动运营",
    ),
    (
        "如何写出可信的实验结论",
        "实验结论需要说明样本、分组、指标和限制。对照组与实验组应尽量控制其他变量，数据来源必须可追溯。使用模拟数据时应醒目标注，不能与真实结果混合表述。",
        "研究方法",
    ),
    (
        "图书馆夜读空间体验观察",
        "夜读空间延长开放后，学生更关注座位供电、照明、安静程度和离场交通。一次体验观察记录了不同时段的使用情况，也收集了学生对预约方式的建议。",
        "校园生活",
    ),
    (
        "新媒体团队的素材归档方法",
        "素材归档应统一日期、活动和摄影者命名规则，保留原图、授权信息与使用记录。公共素材库需要设置清晰权限，避免重复下载和来源不明。",
        "团队协作",
    ),
    (
        "从固定发布时间到个性化推荐",
        "固定发布时间易于执行，但不一定适合每个平台和账号。可解释的时间推荐可以结合平台公开活跃规律与账号历史互动数据，给出分数、理由和备选时段，并通过对照实验验证。",
        "时间推荐",
    ),
]


def seed_demo_business_data(db: Session, roles: dict[str, Role]) -> None:
    operator = db.scalar(select(User).where(User.username == "operator"))
    if not operator:
        return
    if (db.scalar(select(func.count()).select_from(ContentArticle)) or 0) == 0:
        for index, (title, text, topic) in enumerate(ARTICLE_SEEDS):
            article = ContentArticle(
                title=title,
                source_text=text,
                summary=text[:80],
                topic=topic,
                target_audience="校园新媒体运营者",
                tone="专业自然",
                keywords_json=[topic, "内容运营"],
                status="APPROVED" if index < 6 else "GENERATED",
                created_by=operator.id,
            )
            db.add(article)
            db.flush()
            for platform, suffix in (
                ("WEIBO", "观点速览"),
                ("XIAOHONGSHU", "实用清单"),
                ("WECHAT_OFFICIAL", "深度整理"),
            ):
                content = (
                    f"{title}\n\n{text}\n\n这是 {platform} 的 MOCK 演示版本，发布前请人工核验。"
                )
                db.add(
                    ContentVariant(
                        article_id=article.id,
                        platform=platform,
                        version_no=1,
                        title=f"{title}｜{suffix}",
                        content_text=content,
                        hashtags_json=[f"#{topic}", "#校园新媒体"],
                        emoji_count=0,
                        word_count=len(content),
                        model_name="mock-socialflow-v1",
                        prompt_version="1.0.0",
                        generation_duration_ms=320 + index * 7,
                        token_usage=180 + index * 5,
                        quality_score=82 + index % 8,
                        manual_edit_ratio=index % 5,
                        review_status="APPROVED" if index < 6 else "PENDING",
                        original_generated_text=content,
                    )
                )
        db.commit()

    for platform in ("WEIBO", "XIAOHONGSHU", "WECHAT_OFFICIAL"):
        if not db.scalar(
            select(PlatformAccount).where(
                PlatformAccount.user_id == operator.id, PlatformAccount.platform == platform
            )
        ):
            db.add(
                PlatformAccount(
                    user_id=operator.id,
                    platform=platform,
                    account_name=f"SocialFlow 演示{platform}",
                    publish_mode="MOCK",
                    status="ACTIVE",
                )
            )
    db.commit()

    if (db.scalar(select(func.count()).select_from(ActivityPrior)) or 0) == 0:
        peaks = {
            "WEIBO": {8: 78, 12: 82, 18: 88, 20: 96, 21: 91},
            "XIAOHONGSHU": {9: 74, 12: 80, 19: 90, 20: 98, 21: 94, 22: 86},
            "WECHAT_OFFICIAL": {7: 83, 8: 90, 12: 76, 18: 82, 20: 88},
        }
        # 48 half-hour business slots represented as 24 hourly rules for each platform.
        for platform in peaks:
            for hour in range(24):
                db.add(
                    ActivityPrior(
                        platform=platform,
                        day_of_week=0,
                        hour_of_day=hour,
                        base_score=peaks[platform].get(hour, 42 + (hour % 6) * 3),
                        source_description="公开活跃时段经验规则（SIMULATED）",
                    )
                )
        db.commit()

    variants = db.scalars(select(ContentVariant).order_by(ContentVariant.id).limit(20)).all()
    accounts = {
        row.platform: row
        for row in db.scalars(
            select(PlatformAccount).where(PlatformAccount.user_id == operator.id)
        ).all()
    }
    if (db.scalar(select(func.count()).select_from(PublishSchedule)) or 0) == 0:
        now = datetime.now().replace(second=0, microsecond=0)
        for index, variant in enumerate(variants):
            schedule = PublishSchedule(
                article_id=variant.article_id,
                variant_id=variant.id,
                account_id=accounts.get(variant.platform).id
                if accounts.get(variant.platform)
                else None,
                platform=variant.platform,
                scheduled_at=now + timedelta(hours=index + 2),
                publish_mode="MOCK",
                status="PENDING" if index > 5 else "MOCK_SUCCESS",
                retry_count=0,
                max_retry_count=3,
                actual_publish_at=now - timedelta(days=index) if index <= 5 else None,
                published_url=f"mock://socialflow/published/seed-{index}" if index <= 5 else None,
                idempotency_key=str(uuid.uuid4()),
                created_by=operator.id,
            )
            db.add(schedule)
        db.commit()

    schedules = db.scalars(select(PublishSchedule).order_by(PublishSchedule.id).limit(14)).all()
    if schedules and (db.scalar(select(func.count()).select_from(EngagementMetric)) or 0) == 0:
        for index, schedule in enumerate(schedules):
            impressions = 900 + index * 137
            total = 70 + index * 9
            db.add(
                EngagementMetric(
                    schedule_id=schedule.id,
                    platform=schedule.platform,
                    metric_date=date.today() - timedelta(days=13 - index),
                    impressions=impressions,
                    likes=int(total * 0.62),
                    comments=int(total * 0.12),
                    collects=int(total * 0.16),
                    shares=total - int(total * 0.62) - int(total * 0.12) - int(total * 0.16),
                    followers=3000,
                    engagement_total=total,
                    engagement_rate=round(total / impressions, 6),
                    group_type="RECOMMENDED_TIME" if index % 2 == 0 else "FIXED_TIME",
                    data_source="SIMULATED",
                )
            )
        db.commit()

    if (db.scalar(select(func.count()).select_from(Experiment)) or 0) == 0:
        exp1 = Experiment(
            name="AI 辅助内容适配效率实验",
            type="CONTENT_EFFICIENCY",
            hypothesis="AI 初稿可减少人工改写耗时",
            status="RUNNING",
            control_description="纯人工改写",
            treatment_description="AI 生成后人工修改",
            metrics_json={
                "durationMinutes": "完成耗时",
                "editCharacters": "修改字符数",
                "score": "适配评分",
            },
            created_by=operator.id,
            start_date=date.today() - timedelta(days=7),
        )
        exp2 = Experiment(
            name="推荐时间与固定时间对比实验",
            type="PUBLISH_TIME",
            hypothesis="推荐时间组的平均互动率更高",
            status="DRAFT",
            control_description="每日固定 18:00",
            treatment_description="系统推荐时间",
            metrics_json={"engagementRate": "互动率"},
            created_by=operator.id,
        )
        db.add_all([exp1, exp2])
        db.flush()
        for i in range(10):
            db.add(
                ExperimentSample(
                    experiment_id=exp1.id,
                    group_type="CONTROL" if i < 5 else "TREATMENT",
                    sample_label=f"文章样本 {i + 1}（SIMULATED）",
                    metric_value_json={
                        "durationMinutes": 42 - i * 1.5,
                        "editCharacters": 620 - i * 28,
                        "score": 80 + i % 6,
                        "dataSource": "SIMULATED",
                    },
                )
            )
        db.commit()

    setting_defs = [
        ("llm.provider", "mock", False, "大模型提供方"),
        ("llm.base_url", "", False, "OpenAI 兼容接口地址"),
        ("llm.api_key", "", True, "大模型 API Key"),
        ("llm.model", "", False, "模型名称"),
        ("media.unsplash_key", "", True, "Unsplash Access Key"),
        ("publish.mode", "mock", False, "默认发布适配器"),
        ("app.timezone", "Asia/Shanghai", False, "系统时区"),
        ("logs.retention_days", "90", False, "日志保留天数"),
    ]
    for key, value, secret, description in setting_defs:
        if not db.scalar(select(SystemSetting).where(SystemSetting.setting_key == key)):
            db.add(
                SystemSetting(
                    setting_key=key, setting_value=value, is_secret=secret, description=description
                )
            )
    db.commit()


def main() -> None:
    with SessionLocal() as db:
        seed_database(db)
    mode = "with optional demo data" if settings.app_demo_mode else "without demo business data"
    print(f"SocialFlow roles, users and settings are ready ({mode}).")


if __name__ == "__main__":
    main()
