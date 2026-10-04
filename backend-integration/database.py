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


def create_user_submission(
    image_url: str,
    name: str,
    country: str,
    city: str | None = None,
    state: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
):
    query = text(
        """
        INSERT INTO user_submissions (
            url,
            name,
            lat,
            lon,
            city,
            state,
            country
        )
        VALUES (
            :url,
            :name,
            :lat,
            :lon,
            :city,
            :state,
            :country
        )
        """
    )

    with engine.begin() as connection:
        connection.execute(
            query,
            {
                "url": image_url,
                "name": name,
                "lat": lat,
                "lon": lon,
                "city": city,
                "state": state,
                "country": country,
            },
        )

def get_landmark_photos(landmark_id: int, limit: int = 5):
    query = text(
        """
        SELECT DISTINCT url
        FROM training_data
        WHERE landmark_id = :landmark_id
          AND url IS NOT NULL
          AND url <> ''
        LIMIT :limit
        """
    )

    with engine.connect() as connection:
        results = connection.execute(
            query,
            {
                "landmark_id": landmark_id,
                "limit": limit,
            },
        ).scalars().all()

    return list(results)


def get_nearby_landmarks(
    lat: float,
    lon: float,
    exclude_landmark_id: int,
    limit: int = 3,
    max_distance_km: float = 600.0,
):
    import math

    latitude_window = max_distance_km / 111.0
    longitude_scale = max(
        abs(math.cos(math.radians(lat))),
        0.2,
    )
    longitude_window = max_distance_km / (111.0 * longitude_scale)

    query = text(
        """
        WITH candidates AS (
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
              AND landmark_id <> :exclude_landmark_id
              AND lat IS NOT NULL
              AND lon IS NOT NULL
              AND lat BETWEEN :min_lat AND :max_lat
              AND lon BETWEEN :min_lon AND :max_lon
            GROUP BY landmark_id
        ),
        distances AS (
            SELECT
                *,
                6371.0 * ACOS(
                    LEAST(
                        1.0,
                        GREATEST(
                            -1.0,
                            COS(RADIANS(:origin_lat))
                            * COS(RADIANS(lat))
                            * COS(RADIANS(lon) - RADIANS(:origin_lon))
                            + SIN(RADIANS(:origin_lat))
                            * SIN(RADIANS(lat))
                        )
                    )
                ) AS distance_km
            FROM candidates
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
        ORDER BY distance_km
        LIMIT :limit
        """
    )

    with engine.connect() as connection:
        results = connection.execute(
            query,
            {
                "exclude_landmark_id": exclude_landmark_id,
                "origin_lat": lat,
                "origin_lon": lon,
                "min_lat": lat - latitude_window,
                "max_lat": lat + latitude_window,
                "min_lon": lon - longitude_window,
                "max_lon": lon + longitude_window,
                "max_distance_km": max_distance_km,
                "limit": limit,
            },
        ).mappings().all()

    return results
