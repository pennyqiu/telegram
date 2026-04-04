import enum
from sqlalchemy import Integer, String, Text, Date, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class TransferType(str, enum.Enum):
    permanent = "permanent"
    loan = "loan"
    loan_end = "loan_end"
    free = "free"
    youth = "youth"


class Transfer(Base):
    __tablename__ = "transfers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(Integer, ForeignKey("players.id"), nullable=False)
    from_club_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("clubs.id"))
    to_club_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("clubs.id"))
    type: Mapped[TransferType] = mapped_column(String(20), nullable=False)
    transfer_date: Mapped[Date] = mapped_column(Date, nullable=False)
    fee_display: Mapped[str | None] = mapped_column(String(64))
    fee_stars: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    player: Mapped["Player"] = relationship(back_populates="transfers")
    from_club: Mapped["Club | None"] = relationship(foreign_keys=[from_club_id], back_populates="transfers_out")
    to_club: Mapped["Club | None"] = relationship(foreign_keys=[to_club_id], back_populates="transfers_in")


class Retirement(Base):
    __tablename__ = "retirements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(Integer, ForeignKey("players.id"), unique=True)
    retired_at: Mapped[Date] = mapped_column(Date, nullable=False)
    last_club_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("clubs.id"))
    career_summary: Mapped[str | None] = mapped_column(Text)
    achievements: Mapped[list] = mapped_column("achievements_json",
                                               __import__("sqlalchemy").JSON, default=list)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    player: Mapped["Player"] = relationship(back_populates="retirement")
