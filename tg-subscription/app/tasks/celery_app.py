from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery("tg_subscription", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.timezone = "Asia/Shanghai"
celery_app.conf.beat_schedule = {
    "check-expiring": {"task": "check_expiring_subscriptions", "schedule": crontab(hour=10, minute=0)},
    "expire-subs": {"task": "expire_subscriptions", "schedule": crontab(minute=0)},
    # 每天 07:00 Asia/Shanghai 抓取投资大师最新内容
    "fetch-influencer-updates": {
        "task": "fetch_influencer_updates",
        "schedule": crontab(hour=7, minute=0),
    },
    # 每天 08:00 Asia/Shanghai 生成普通话播客音频摘要
    "translate-podcasts": {
        "task": "translate_podcasts",
        "schedule": crontab(hour=8, minute=0),
    },
}
celery_app.autodiscover_tasks(["app.tasks"])
