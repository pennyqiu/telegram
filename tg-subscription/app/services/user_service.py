from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import User


class UserService:

    async def get_or_create(self, db: AsyncSession, tg_data: dict) -> User:
        telegram_id = int(tg_data["id"])
        result = await db.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if user:
            user.first_name = tg_data.get("first_name", user.first_name)
            user.username = tg_data.get("username")
        else:
            user = User(
                telegram_id=telegram_id,
                first_name=tg_data.get("first_name", ""),
                last_name=tg_data.get("last_name"),
                username=tg_data.get("username"),
                language_code=tg_data.get("language_code", "zh"),
            )
            db.add(user)
            await db.flush()
        return user

    async def get_by_telegram_id(self, db: AsyncSession, telegram_id: int) -> User | None:
        result = await db.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()


user_service = UserService()
