import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv(Path(__file__).with_name('.env'))

# URL.create protège les caractères spéciaux du mot de passe Oracle.
DATABASE_URL = (
    make_url(os.environ['DATABASE_URL'])
    if os.getenv('DATABASE_URL')
    else URL.create(
        'oracle+oracledb',
        username=os.getenv('DATABASE_USER'),
        password=os.getenv('DATABASE_PASSWORD'),
        host=os.getenv('DATABASE_HOST', 'localhost'),
        port=int(os.getenv('DATABASE_PORT', '1521')),
        query={'service_name': os.getenv('DATABASE_SERVICE', 'FREEPDB1')},
    )
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)


class Base(DeclarativeBase):
    pass


SessionLocal = sessionmaker(bind=engine, autoflush=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
