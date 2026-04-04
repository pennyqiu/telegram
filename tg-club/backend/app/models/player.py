import enum
from sqlalchemy import Integer, SmallInteger, String, Boolean, Text, Date, DateTime, Numeric, ForeignKey, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class PlayerStatus(str, enum.Enum):
    active = "active"
    retired = "retired"
    free_agent = "free_agent"
    loan = "loan"


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    current_club_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("clubs.id"))

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(128))
    photo_url: Mapped[str | None] = mapped_column(String(512))
    birth_date: Mapped[Date | None] = mapped_column(Date)
    nationality: Mapped[str | None] = mapped_column(String(64))
    position: Mapped[str | None] = mapped_column(String(8))
    status: Mapped[PlayerStatus] = mapped_column(String(20), default=PlayerStatus.active)

    height_cm: Mapped[int | None] = mapped_column(SmallInteger)
    weight_kg: Mapped[int | None] = mapped_column(SmallInteger)
    preferred_foot: Mapped[str | None] = mapped_column(String(8))

    bio: Mapped[str | None] = mapped_column(Text)
    market_value: Mapped[int | None] = mapped_column(Integer)
    jersey_number: Mapped[int | None] = mapped_column(SmallInteger)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    rating: Mapped[float | None] = mapped_column(Numeric(3, 1))

    access_tier: Mapped[str] = mapped_column(String(16), default="basic")
    retired_at: Mapped[Date | None] = mapped_column(Date)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    current_club: Mapped["Club | None"] = relationship(back_populates="players")
    transfers: Mapped[list["Transfer"]] = relationship(back_populates="player", order_by="Transfer.transfer_date.desc()")
    retirement: Mapped["Retirement | None"] = relationship(back_populates="player")
