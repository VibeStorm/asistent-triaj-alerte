"""Conexiunea la baza SQLite și modelul tabelului de evenimente."""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

DEFAULT_DB_URL = "sqlite:///events.db"


class Base(DeclarativeBase):
    pass


class SecurityEvent(Base):
    """Un eveniment de autentificare Windows (4624 = reușit, 4625 = eșuat)."""

    __tablename__ = "security_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)  # UTC, fără fus în obiect
    event_id: Mapped[int] = mapped_column(Integer, index=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    source_ip: Mapped[str] = mapped_column(String(45), index=True)
    workstation: Mapped[str] = mapped_column(String(64))
    logon_type: Mapped[int] = mapped_column(Integer)  # 3 = rețea, 10 = RDP etc.


def make_session_factory(url: str = DEFAULT_DB_URL) -> sessionmaker[Session]:
    """Creează tabelele (dacă lipsesc) și întoarce o fabrică de sesiuni."""
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    return sessionmaker(engine)
