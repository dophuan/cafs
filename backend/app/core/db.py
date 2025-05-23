from sqlmodel import Session, create_engine, select
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app import crud
from app.core.config import settings
from app.models.user import User, UserCreate

engine = create_engine(
    str(settings.SQLALCHEMY_DATABASE_URI),
    pool_size=5,
    max_overflow=10,
    pool_timeout=30
)

print(f"----- DATABASE URI: {settings.SQLALCHEMY_DATABASE_URI} -----")

@event.listens_for(Engine, "connect")
def connect(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
    cursor.close()

def init_db(session: Session) -> None:
    # Tables should be created with Alembic migrations
    # But if you don't want to use migrations, create
    # the tables un-commenting the next lines
    # from sqlmodel import SQLModel

    # This works because the models are already imported and registered from app.models
    # SQLModel.metadata.create_all(engine)

    user = session.exec(
        select(User).where(User.email == settings.FIRST_SUPERUSER)
    ).first()
    if not user:
        user_in = UserCreate(
            email=settings.FIRST_SUPERUSER,
            password=settings.FIRST_SUPERUSER_PASSWORD,
            is_superuser=True,
        )
        user = crud.create_user(session=session, user_create=user_in)