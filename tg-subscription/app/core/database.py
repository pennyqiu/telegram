from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings


def _make_engine():
    url = settings.database_url
    if not url:
        return None
    return create_async_engine(url, pool_pre_ping=True, echo=False)


engine = _make_engine()
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False) if engine else None


class Base(DeclarativeBase):
    pass


# 显式导入所有 Model，确保 Base.metadata 包含所有表
def _import_models():
    from app.models import user, plan, subscription, payment, payment_order, course_credential  # noqa: F401

_import_models()


async def get_db() -> AsyncSession:
    if AsyncSessionLocal is None:
        raise RuntimeError("DATABASE_URL 未配置，数据库不可用")
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
