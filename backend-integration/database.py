import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set in the .env file.")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def check_database_connection():
    """Checks that the backend can successfully connect to Neon."""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    return True


def get_landmark(landmark_id: int):
    """Returns the same first row for a landmark while its database rows are unchanged."""
    with engine.connect() as connection:
        result = connection.execute(
            text(
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
                -- A landmark has multiple photo rows. Choose by a stable ID
                -- so separate uploads do not select an arbitrary database row.
                ORDER BY id ASC NULLS LAST
                LIMIT 1
                """
            ),
            {"landmark_id": landmark_id},
        ).mappings().first()

    return dict(result) if result else None


def get_landmark_photos(landmark_id: int, limit: int = 5):
    """Returns unique Neon image URLs in a consistent order for this landmark."""
    with engine.connect() as connection:
        results = connection.execute(
            text(
                """
                SELECT DISTINCT url
                FROM training_data
                WHERE landmark_id = :landmark_id
                  AND url IS NOT NULL
                  AND TRIM(url) <> ''
                -- DISTINCT URLs also need an order before applying the limit.
                ORDER BY url ASC
                LIMIT :limit
                """
            ),
            {
                "landmark_id": landmark_id,
                "limit": limit,
            },
        ).mappings().all()

    return [row["url"] for row in results if row.get("url")]


def get_nearby_landmarks(
    lat: float,
    lon: float,
    landmark_id: int,
    limit: int = 3,
    max_distance_km: float = 600.0,
):
    """Returns nearby distinct landmarks using latitude and longitude."""
    query = text(
        """
        WITH landmark_groups AS (
            SELECT
                landmark_id,
                MAX(name) AS name,
                MAX(category_name) AS category_name,
                MAX(city) AS city,
                MAX(state) AS state,
                MAX(country) AS country,
                AVG(lat) AS lat,
                AVG(lon) AS lon,
                MAX(url) AS url
            FROM training_data
            WHERE landmark_id IS NOT NULL
              AND lat IS NOT NULL
              AND lon IS NOT NULL
              AND landmark_id <> :landmark_id
            GROUP BY landmark_id
        ),
        distances AS (
            SELECT
                landmark_id,
                name,
                category_name,
                city,
                state,
                country,
                lat,
                lon,
                url,
                (
                    6371 * acos(
                        LEAST(
                            1,
                            GREATEST(
                                -1,
                                cos(radians(:lat))
                                * cos(radians(lat))
                                * cos(radians(lon) - radians(:lon))
                                + sin(radians(:lat))
                                * sin(radians(lat))
                            )
                        )
                    )
                ) AS distance_km
            FROM landmark_groups
        )
        SELECT
            landmark_id,
            name,
            category_name,
            city,
            state,
            country,
            lat,
            lon,
            url,
            distance_km
        FROM distances
        WHERE distance_km <= :max_distance_km
        ORDER BY distance_km ASC
        LIMIT :limit
        """
    )

    with engine.connect() as connection:
        results = connection.execute(
            query,
            {
                "lat": lat,
                "lon": lon,
                "landmark_id": landmark_id,
                "max_distance_km": max_distance_km,
                "limit": limit,
            },
        ).mappings().all()

    return [dict(row) for row in results]


def create_user_submission(
    image_url: str,
    name: str,
    country: str,
    city=None,
    state=None,
    lat=None,
    lon=None,
):
    """Creates a new pending user submission."""
    with engine.begin() as connection:
        result = connection.execute(
            text(
                """
                INSERT INTO user_submissions (
                    url,
                    name,
                    lat,
                    lon,
                    city,
                    state,
                    country,
                    status
                )
                VALUES (
                    :url,
                    :name,
                    :lat,
                    :lon,
                    :city,
                    :state,
                    :country,
                    'pending'
                )
                RETURNING submission_id
                """
            ),
            {
                "url": image_url,
                "name": name,
                "lat": lat,
                "lon": lon,
                "city": city,
                "state": state,
                "country": country,
            },
        ).scalar_one()

    return result


def get_pending_submissions():
    """Returns all user submissions that are still waiting for review."""
    with engine.connect() as connection:
        results = connection.execute(
            text(
                """
                SELECT *
                FROM user_submissions
                WHERE status = 'pending'
                   OR status IS NULL
                ORDER BY submission_id ASC
                """
            )
        ).mappings().all()

    return [dict(row) for row in results]


def get_non_migrated_submissions():
    """
    Returns reviewed submissions that have not been migrated yet.

    This includes approved and rejected submissions so the admin can
    correct an accidental decision before the migration step.
    """
    with engine.connect() as connection:
        results = connection.execute(
            text(
                """
                SELECT *
                FROM user_submissions
                WHERE status IN ('approved', 'rejected')
                ORDER BY submission_id ASC
                """
            )
        ).mappings().all()

    return [dict(row) for row in results]


def train_search(search_text: str):
    """
    Searches training_data by landmark name or category name.

    This lets the admin check whether a landmark already exists and
    see which category_name values are currently being used.
    """
    pattern = f"%{search_text.strip()}%"

    with engine.connect() as connection:
        results = connection.execute(
            text(
                """
                SELECT DISTINCT
                    landmark_id,
                    category_name,
                    name,
                    city,
                    state,
                    country
                FROM training_data
                WHERE name ILIKE :pattern
                   OR category_name ILIKE :pattern
                ORDER BY name ASC NULLS LAST
                LIMIT 100
                """
            ),
            {"pattern": pattern},
        ).mappings().all()

    return [dict(row) for row in results]


def approve_submission(submission_id: int, info=None):
    """
    Marks a submission as approved.

    If the frontend sends corrected information, that information is saved
    at the same time before the status changes.
    """
    values = {
        "submission_id": submission_id,
        "url": None,
        "landmark_id": None,
        "category_name": None,
        "name": None,
        "lat": None,
        "lon": None,
        "city": None,
        "state": None,
        "country": None,
    }

    if info:
        if hasattr(info, "model_dump"):
            incoming = info.model_dump()
        elif isinstance(info, dict):
            incoming = info
        else:
            incoming = {}

        for key in values:
            if key != "submission_id" and key in incoming:
                values[key] = incoming[key]

    with engine.begin() as connection:
        result = connection.execute(
            text(
                """
                UPDATE user_submissions
                SET
                    url = COALESCE(:url, url),
                    landmark_id = COALESCE(:landmark_id, landmark_id),
                    category_name = COALESCE(:category_name, category_name),
                    name = COALESCE(:name, name),
                    lat = COALESCE(:lat, lat),
                    lon = COALESCE(:lon, lon),
                    city = COALESCE(:city, city),
                    state = COALESCE(:state, state),
                    country = COALESCE(:country, country),
                    status = 'approved'
                WHERE submission_id = :submission_id
                """
            ),
            values,
        )

    return result.rowcount > 0


def reject_submission(submission_id: int):
    """Marks a submission as rejected without deleting it."""
    with engine.begin() as connection:
        result = connection.execute(
            text(
                """
                UPDATE user_submissions
                SET status = 'rejected'
                WHERE submission_id = :submission_id
                """
            ),
            {"submission_id": submission_id},
        )

    return result.rowcount > 0


def update_submission(submission_id: int, info):
    """Updates editable fields on a user submission."""
    if hasattr(info, "model_dump"):
        incoming = info.model_dump()
    elif isinstance(info, dict):
        incoming = info
    else:
        incoming = {}

    values = {
        "submission_id": submission_id,
        "url": incoming.get("url"),
        "landmark_id": incoming.get("landmark_id"),
        "category_name": incoming.get("category_name"),
        "name": incoming.get("name"),
        "lat": incoming.get("lat"),
        "lon": incoming.get("lon"),
        "city": incoming.get("city"),
        "state": incoming.get("state"),
        "country": incoming.get("country"),
        "status": incoming.get("status"),
    }

    with engine.begin() as connection:
        result = connection.execute(
            text(
                """
                UPDATE user_submissions
                SET
                    url = COALESCE(:url, url),
                    landmark_id = COALESCE(:landmark_id, landmark_id),
                    category_name = COALESCE(:category_name, category_name),
                    name = COALESCE(:name, name),
                    lat = COALESCE(:lat, lat),
                    lon = COALESCE(:lon, lon),
                    city = COALESCE(:city, city),
                    state = COALESCE(:state, state),
                    country = COALESCE(:country, country),
                    status = COALESCE(:status, status)
                WHERE submission_id = :submission_id
                """
            ),
            values,
        )

    return result.rowcount > 0


def delete_submission(submission_id: int):
    """Deletes a user submission completely."""
    with engine.begin() as connection:
        result = connection.execute(
            text(
                """
                DELETE FROM user_submissions
                WHERE submission_id = :submission_id
                """
            ),
            {"submission_id": submission_id},
        )

    return result.rowcount > 0


def clean_tables():
    """
    Moves reviewed submissions out of user_submissions.

    Approved rows are copied to training_data and migrated_submissions.
    Rejected rows are copied to migrated_submissions only.

    After the copy succeeds, the reviewed rows are removed from
    user_submissions.
    """
    with engine.begin() as connection:
        approved_rows = connection.execute(
            text(
                """
                SELECT *
                FROM user_submissions
                WHERE status = 'approved'
                """
            )
        ).mappings().all()

        rejected_rows = connection.execute(
            text(
                """
                SELECT *
                FROM user_submissions
                WHERE status = 'rejected'
                """
            )
        ).mappings().all()

        approved_count = 0
        rejected_count = 0

        for row in approved_rows:
            row_data = dict(row)

            connection.execute(
                text(
                    """
                    INSERT INTO training_data (
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
                    )
                    VALUES (
                        :id,
                        :url,
                        :landmark_id,
                        :category_name,
                        :name,
                        :lat,
                        :lon,
                        :city,
                        :state,
                        :country
                    )
                    ON CONFLICT DO NOTHING
                    """
                ),
                {
                    "id": row_data.get("id"),
                    "url": row_data.get("url"),
                    "landmark_id": row_data.get("landmark_id"),
                    "category_name": row_data.get("category_name"),
                    "name": row_data.get("name"),
                    "lat": row_data.get("lat"),
                    "lon": row_data.get("lon"),
                    "city": row_data.get("city"),
                    "state": row_data.get("state"),
                    "country": row_data.get("country"),
                },
            )

            connection.execute(
                text(
                    """
                    INSERT INTO migrated_submissions (
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
                    )
                    VALUES (
                        :id,
                        :url,
                        :landmark_id,
                        :category_name,
                        :name,
                        :lat,
                        :lon,
                        :city,
                        :state,
                        :country
                    )
                    ON CONFLICT DO NOTHING
                    """
                ),
                {
                    "id": row_data.get("id"),
                    "url": row_data.get("url"),
                    "landmark_id": row_data.get("landmark_id"),
                    "category_name": row_data.get("category_name"),
                    "name": row_data.get("name"),
                    "lat": row_data.get("lat"),
                    "lon": row_data.get("lon"),
                    "city": row_data.get("city"),
                    "state": row_data.get("state"),
                    "country": row_data.get("country"),
                },
            )

            approved_count += 1

        for row in rejected_rows:
            row_data = dict(row)

            connection.execute(
                text(
                    """
                    INSERT INTO migrated_submissions (
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
                    )
                    VALUES (
                        :id,
                        :url,
                        :landmark_id,
                        :category_name,
                        :name,
                        :lat,
                        :lon,
                        :city,
                        :state,
                        :country
                    )
                    ON CONFLICT DO NOTHING
                    """
                ),
                {
                    "id": row_data.get("id"),
                    "url": row_data.get("url"),
                    "landmark_id": row_data.get("landmark_id"),
                    "category_name": row_data.get("category_name"),
                    "name": row_data.get("name"),
                    "lat": row_data.get("lat"),
                    "lon": row_data.get("lon"),
                    "city": row_data.get("city"),
                    "state": row_data.get("state"),
                    "country": row_data.get("country"),
                },
            )

            rejected_count += 1

        connection.execute(
            text(
                """
                DELETE FROM user_submissions
                WHERE status IN ('approved', 'rejected')
                """
            )
        )

    return {
        "approved_migrated": approved_count,
        "rejected_archived": rejected_count,
    }
