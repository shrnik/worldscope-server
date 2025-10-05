import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Float
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB
from dotenv import load_dotenv

load_dotenv()


def get_database_url():
    user = os.getenv("DB_USER", "user")
    password = os.getenv("DB_PASSWORD", "password")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    database = os.getenv("DB_DATABASE", "dbname")
    ssl = os.getenv("DB_SSL", "false").lower() == "true"

    ssl_mode = "?sslmode=require" if ssl else ""
    return f"postgresql://{user}:{password}@{host}:{port}/{database}{ssl_mode}"
DATABASE_URL = get_database_url()
print(f"Connecting to database at {DATABASE_URL}")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Image(Base):
    __tablename__ = "images_v2"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String)
    camera_id = Column(String, unique=True)
    embedding = Column(Vector(768))
    created_at = Column(DateTime, server_default=text('now()'))
    updated_at = Column(DateTime, server_default=text('now()'), onupdate=text('now()'))
    camera_data = Column(JSONB)
    contrail_probability = Column(Float, nullable=True)


def check_tables_exist():
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'images_v2'
            );
        """))
        exists = result.scalar()
    return exists

def create_db_and_tables():
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(bind=engine)

# export the connection and session
db = engine

create_db_and_tables()