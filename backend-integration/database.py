import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is missing. Add it to backend-integration/.env."
    )


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)


def check_database_connection():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    return True


def get_landmark(landmark_id: int):
    query = text(
        """
        SELECT
            id,
            url,
            landmark_id,
            category_name,
            name,
            lat,
            lon,
            city,
            state,
            country
        FROM training_data
        WHERE landmark_id = :landmark_id
        LIMIT 1
        """
    )

    with engine.connect() as connection:
        result = connection.execute(
            query,
            {"landmark_id": landmark_id},
        ).mappings().first()

    return result