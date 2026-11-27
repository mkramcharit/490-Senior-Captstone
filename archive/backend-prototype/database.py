import os

from sqlalchemy import create_engine, text

engine = create_engine(
    os.environ["DATABASE_URL"]
)


def get_landmark(landmark_id: int):

    with engine.connect() as connection:
        result = connection.execute(
            text("""
                SELECT *
                FROM training_data
                WHERE landmark_id = :landmark_id
                LIMIT 1
            """),
            {"landmark_id": landmark_id}
        ).mappings().first()

    return result
  