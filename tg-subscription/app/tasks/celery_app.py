from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "tg_subscription",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.subscription_tasks",
        "app.tasks.influencer_tracker",
        "app.tasks.podcast_translator",
    ],
)
celery_app.conf.timezone = "Asia/Shanghai"
celery_app.conf.beat_schedule = {
    "check-expiring": {"task": "check_expiring_subscriptions", "schedule": crontab(hour=10, minute=0)},
    "expire-subs": {"task": "expire_subscriptions", "schedule": crontab(minute=0)},
    "fetch-influencer-updates": {
        "task": "fetch_influencer_updates",
        "schedule": crontab(hour=7, minute=0),
    },
    "translate-podcasts": {
        "task": "translate_podcasts",
        "schedule": crontab(hour=8, minute=0),
    },
}
