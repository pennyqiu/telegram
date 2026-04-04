import enum
from datetime import datetime
from sqlalchemy import Boolean, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class AdminRole(str, enum.Enum):
    admin  = "admin"   # 超级管理员：全权限 + 管理编辑账号
    editor = "editor"  # 编辑员：可增删改俱乐部/球员/转会，不能管理账号


class AdminUser(Base):
    __tablename__ = "admin_users"

    id:            Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    username:      Mapped[str]           = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str]           = mapped_column(String(256), nullable=False)
    role:          Mapped[str]           = mapped_column(String(16), default=AdminRole.editor, nullable=False)
    is_active:     Mapped[bool]          = mapped_column(Boolean, default=True)
    created_by:    Mapped[str | None]    = mapped_column(String(64))     # 创建者用户名
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at:    Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:    Mapped[datetime]      = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
