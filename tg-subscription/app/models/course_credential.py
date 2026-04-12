from datetime import datetime
from sqlalchemy import BigInteger, Boolean, String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class CourseCredential(Base):
    __tablename__ = "course_credentials"

    id:           Mapped[int]      = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_id:  Mapped[int]      = mapped_column(BigInteger, unique=True, nullable=False)
    login:        Mapped[str]      = mapped_column(String(64), unique=True, nullable=False)  # tg_<id>
    password_hash: Mapped[str]     = mapped_column(String(64), nullable=False)              # SHA-256
    display_name: Mapped[str]      = mapped_column(String(128), nullable=False)
    session_token: Mapped[str | None] = mapped_column(String(128))
    is_active:    Mapped[bool]     = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:   Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
