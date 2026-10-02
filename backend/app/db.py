import hashlib
from collections.abc import Generator
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    select,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)


engine = create_engine(
    "sqlite:///./app.db",
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(connection, _record) -> None:
    connection.execute("PRAGMA foreign_keys=ON")


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="ck_users_email_lowercase"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="1",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    documents: Mapped[list["Document"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class LoginEvent(Base):
    __tablename__ = "login_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("user_id", "sha256", name="uq_documents_user_sha256"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    user: Mapped["User"] = relationship(back_populates="documents")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="document",
        order_by="Message.id",
        cascade="all, delete-orphan",
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant')",
            name="ck_messages_role",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    document: Mapped["Document"] = relationship(back_populates="messages")


Base.metadata.create_all(engine)


def _migrate_legacy_documents() -> None:
    with engine.connect() as connection:
        columns = {
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(documents)"
            )
        }
        if not columns or "user_id" in columns:
            return

        connection.commit()
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        try:
            with connection.begin():
                created_at = datetime.now(timezone.utc).isoformat()
                connection.exec_driver_sql(
                    """
                    INSERT OR IGNORE INTO users (email, password_hash, created_at)
                    VALUES ('legacy-data@invalid.local', '', ?)
                    """,
                    (created_at,),
                )
                legacy_user_id = connection.exec_driver_sql(
                    "SELECT id FROM users WHERE email = 'legacy-data@invalid.local'"
                ).scalar_one()
                connection.exec_driver_sql(
                    """
                    CREATE TABLE documents_new (
                        id INTEGER NOT NULL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id),
                        filename VARCHAR(255) NOT NULL,
                        sha256 VARCHAR(64) NOT NULL,
                        text TEXT NOT NULL,
                        summary_json TEXT,
                        created_at DATETIME NOT NULL,
                        CONSTRAINT uq_documents_user_sha256 UNIQUE (user_id, sha256)
                    )
                    """
                )
                connection.exec_driver_sql(
                    """
                    INSERT INTO documents_new
                        (id, user_id, filename, sha256, text, summary_json, created_at)
                    SELECT id, ?, filename, sha256, text, summary_json, created_at
                    FROM documents
                    """,
                    (legacy_user_id,),
                )
                connection.exec_driver_sql("DROP TABLE documents")
                connection.exec_driver_sql(
                    "ALTER TABLE documents_new RENAME TO documents"
                )
                connection.exec_driver_sql(
                    "CREATE INDEX ix_documents_user_id ON documents (user_id)"
                )
        finally:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()


_migrate_legacy_documents()


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def get_or_create_document(
    session: Session,
    user_id: int,
    filename: str,
    sha256: str,
    text: str,
) -> Document:
    document = session.scalar(
        select(Document).where(
            Document.user_id == user_id,
            Document.sha256 == sha256,
        )
    )
    if document is not None:
        return document

    document = Document(
        user_id=user_id,
        filename=filename,
        sha256=sha256,
        text=text,
    )
    session.add(document)
    session.flush()
    return document


def get_recent_messages(
    session: Session,
    document_id: int,
    limit: int = 8,
) -> list[dict]:
    messages = session.scalars(
        select(Message)
        .where(Message.document_id == document_id)
        .order_by(Message.id.desc())
        .limit(limit)
    ).all()
    return [
        {"role": message.role, "content": message.content}
        for message in reversed(messages)
    ]
