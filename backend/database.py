from sqlalchemy import create_engine, text

engine = create_engine(
    "postgresql://landmarks_owner:npg_jcmM5DsKEr1b@ep-dry-breeze-a5wcb604-pooler.us-east-2.aws.neon.tech/landmarks?sslmode=require&channel_binding=require"
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
  