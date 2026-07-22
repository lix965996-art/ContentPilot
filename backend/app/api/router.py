from fastapi import APIRouter

from app.api.endpoints import (
    admin,
    analytics,
    articles,
    auth,
    dashboard,
    experiments,
    generation,
    health,
    media,
    platform_accounts,
    recommendations,
    schedules,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(dashboard.router)
api_router.include_router(articles.router)
api_router.include_router(generation.router)
api_router.include_router(media.router)
api_router.include_router(platform_accounts.router)
api_router.include_router(recommendations.router)
api_router.include_router(schedules.router)
api_router.include_router(analytics.router)
api_router.include_router(experiments.router)
api_router.include_router(admin.router)
