import enum
from sqlalchemy import Integer, String, Boolean, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class ClubStatus(str, enum.Enum):
    active = "active"
    disbanded = "disbanded"
    merged = "merged"


class Club(Base):
    __tablename__ = "clubs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    league_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("leagues.id"))
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(32))
    logo_url: Mapped[str | None] = mapped_column(String(512))
    country: Mapped[str | None] = mapped_column(String(64))
    founded_year: Mapped[int | None] = mapped_column(Integer)
    stadium: Mapped[str | None] = mapped_column(String(128))
    stadium_capacity: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ClubStatus] = mapped_column(String(20), default=ClubStatus.active)
    access_tier: Mapped[str] = mapped_column(String(16), default="basic")
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    league: Mapped["League | None"] = relationship(back_populates="clubs")
    players: Mapped[list["Player"]] = relationship(back_populates="current_club")
    transfers_in: Mapped[list["Transfer"]] = relationship(
        foreign_keys="Transfer.to_club_id", back_populates="to_club"
    )
    transfers_out: Mapped[list["Transfer"]] = relationship(
        foreign_keys="Transfer.from_club_id", back_populates="from_club"
    )
