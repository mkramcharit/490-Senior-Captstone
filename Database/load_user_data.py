# This file contains the FastAPI code for handling admin review of user submissions
#
# 2026 - Christopher Hochrein

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import boto3
import os
import uuid

load_dotenv()

BUCKET_NAME = "image-bucket"
BASE_URL = os.environ["ENDPOINT_URL_S3"] + "/" + BUCKET_NAME

app = FastAPI(title="Ladmark Submission API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)  # CORS middleware for handling cross-origin requests

engine = create_engine(
    os.environ["DATABASE_URL"], pool_pre_ping=True
)  # Neon connection object

client = boto3.client(
    "s3",
    region_name=os.environ["REGION"],
    endpoint_url=os.environ["ENDPOINT_URL_S3"],
    aws_access_key_id=os.environ["TOKEN_ID"],
    aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
)  # S3 client for handling image uploads


class SubmissionInfo(BaseModel):
    category_name: str
    name: str | None = None
    lat: float
    lon: float
    city: str | None = None
    state: str | None = None
    country: str | None = None


def upload_image(image: UploadFile):
    """Function to upload image to S3 bucket"""
    extension = image.filename.split(".")[-1] if "." in image.filename else "jpg"

    key = f"{uuid.uuid4().hex}.{extension}"
    client.upload_fileobj(image.file, BUCKET_NAME, key)

    return f"{BASE_URL}/{key}"


@app.post("/submission")
def new_submission(
    image: UploadFile = File(...),
    name: str = Form(..., description="Name of the landmark"),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    city: str | None = Form(None),
    state: str | None = Form(None),
    country: str = Form(...),
):
    """Post method for user submission"""
    url = upload_image(image)
    with engine.begin() as connection:
        connection.execute(
            text("""
            INSERT INTO user_submissions (url, name, lat, lon, city, state, country)
            VALUES (:url, :name, :lat, :lon, :city, :state, :country)"""),
            {
                "url": url,
                "name": name,
                "lat": lat,
                "lon": lon,
                "city": city,
                "state": state,
                "country": country,
            },
        )
    return "Accepted"


# To-do: Set up an index to make this faster
@app.get("/admin/train-search/{name}")
def train_search(input_name: str):
    """Search training_data table for specific name and return the number of landmarks for that name"""
    with engine.begin() as connection:
        result = connection.execute(
            text("""
            SELECT * FROM training_data
            WHERE name ILIKE :match
            GROUP BY name, category_name, landmark_id
            LIMIT 100"""),
            {
                "match": f"%{input_name}%",
            },
        )
        result = [dict(row._mapping) for row in result]

        landmark_count = connection.execute(
            text("""
            SELECT COUNT(DISTINCT name)
            FROM training_data
            WHERE name ILIKE :match"""),
            {
                "match": f"%{input_name}%",
            },
        ).scalar()

        return {"results": result, "landmark_count": landmark_count}


@app.get("/admin/pending")
def get_pending_submissions():
    """Get all pending submissions for admin review"""
    with engine.begin() as connection:
        result = connection.execute(text("""
            SELECT * FROM user_submissions
            WHERE status = 'pending'
        """))
        return [dict(row._mapping) for row in result]


@app.get("/admin/non-migrated")
def get_non_migrated_submissions():
    """Get all non-migrated submissions for admin review"""
    with engine.begin() as connection:
        result = connection.execute(text("""
            SELECT * FROM user_submissions
            WHERE status = 'approved' or status = 'rejected'
        """))
        return [dict(row._mapping) for row in result]


@app.get("/admin/migrated")
def get_migrated_submissions():
    """Get row data for migrated submissions from migrated_submissions table"""
    with engine.begin() as connection:
        result = connection.execute(text("""
            SELECT * FROM migrated_submissions
        """))
        return [dict(row._mapping) for row in result]


@app.post("/admin/unmark/{submission_id}")
def unmark_approved(submission_id: int):
    """Post for admin changing a submissision from approved to pending"""
    with engine.begin() as connection:
        result = connection.execute(
            text("""
            UPDATE user_submissions
            SET status = 'pending'
            WHERE submission_id = :submission_id"""),
            {
                "submission_id": submission_id,
            },
        )

    if result.rowcount == 0:
        raise HTTPException(404, detail="Error: No matching item")

    return {"status": "Submission unmarked"}


# To-do: consider editing this function to clean up after messy admin input
def format_category_name(category_name: str):
    """This function ensures category_name is properly formatted as: 'Category:Category_Name'"""
    names = category_name.split(" ")
    capital_names = []

    for name in names:
        capital_names.append(name.capitalize())
    proper_name = "_".join(capital_names)

    return "Category:" + proper_name


@app.post("/admin/approve/{submission_id}")
def approve_submission(submission_id: int, info: SubmissionInfo):
    """Post for admin approving a submission"""
    category_name = format_category_name(info.category_name)
    with engine.begin() as connection:
        result = connection.execute(
            text("""
            UPDATE user_submissions
            SET status = 'approved',
            category_name = :category_name,
            name = :name,
            lat = :lat,
            lon = :lon,
            city = :city,
            state = :state,
            country = :country
            WHERE submission_id = :submission_id"""),
            {
                "submission_id": submission_id,
                "category_name": category_name,
                "name": info.name,
                "lat": info.lat,
                "lon": info.lon,
                "city": info.city,
                "state": info.state,
                "country": info.country,
            },
        )

    if result.rowcount == 0:
        raise HTTPException(404, detail="Error: No matching item")

    return {"status": "Submission approved"}


@app.post("/admin/reject/{submission_id}")
def reject_submission(submission_id: int):
    """Post for when admin rejects a submission"""
    with engine.begin() as connection:
        result = connection.execute(
            text("""
            UPDATE user_submissions
            SET status = 'rejected'
            WHERE submission_id = :submission_id"""),
            {
                "submission_id": submission_id,
            },
        )

    if result.rowcount == 0:
        raise HTTPException(404, detail="Error: No matching item")

    return {"status": "Submission rejected"}


def get_approved(connection):
    """Fetch all approved submissions from the user_submissions table"""
    approved = connection.execute(text("""
        SELECT * FROM user_submissions
        WHERE status = 'approved'
    """))
    return approved.fetchall()


def fetch_landmark_id(connection, category_name: str):
    """Fetch the landmark_id for a given category_name from the training_data table, or create one"""
    result = connection.execute(
        text("""
        SELECT landmark_id FROM training_data
        WHERE category_name = :category_name 
        LIMIT 1
        """),
        {"category_name": category_name},
    ).scalar()  # scalar() because we only expect one result
    if result is not None:
        return result
    else:
        new_id = connection.execute(text("""
            SELECT COALESCE(MAX(landmark_id), 0) + 1
            FROM training_data""")).scalar()
        return new_id


def move_approved(connection, landmark_id, submission):
    """Function to move approved submissions to the training_data and migrated_submissions tables"""
    id = uuid.uuid4().hex[:16]
    connection.execute(
        text("""
        INSERT INTO training_data (id, url, landmark_id, category_name, name, lat, lon, country, city, state)
        VALUES (:id, :url, :landmark_id, :category_name, :name, :lat, :lon, :country, :city, :state)
        """),
        {
            "id": id,
            "url": submission.url,
            "landmark_id": landmark_id,
            "category_name": submission.category_name,
            "name": submission.name,
            "lat": submission.lat,
            "lon": submission.lon,
            "country": submission.country,
            "city": submission.city,
            "state": submission.state,
        },
    )

    connection.execute(
        text("""
            INSERT INTO migrated_submissions (id, url, landmark_id, category_name, name, lat, lon, country, city, state)
            VALUES (:id, :url, :landmark_id, :category_name, :name, :lat, :lon, :country, :city, :state)
            """),
        {
            "id": id,
            "url": submission.url,
            "landmark_id": landmark_id,
            "category_name": submission.category_name,
            "name": submission.name,
            "lat": submission.lat,
            "lon": submission.lon,
            "country": submission.country,
            "city": submission.city,
            "state": submission.state,
        },
    )

    connection.execute(
        text("""
        DELETE FROM user_submissions
        WHERE submission_id = :submission_id
        """),
        {
            "submission_id": submission.submission_id,
        },
    )


@app.post("/admin/clean")
def clean_tables():
    """Post method for migrating approved entries from user_submission table"""
    migrate_count = []
    fail_count = []

    with engine.begin() as connection:
        approved_submission = get_approved(connection)
        for submission in approved_submission:
            # We use a try/except block so we can continue processing other submissions even if one fails
            try:
                # begin_nested prevents duplicates if the move_approved call fails partway through (not sure if that can happen)
                with connection.begin_nested():
                    new_landmark_id = fetch_landmark_id(
                        connection, submission.category_name
                    )
                    move_approved(connection, new_landmark_id, submission)
                migrate_count.append({"submission_id": submission.submission_id, "status": "migrated"})
            except Exception as e:
                fail_count.append({"submission_id": submission.submission_id, "status": "Error: Migration failed"})

        if not migrate_count and not fail_count:
            return {"status": "no approved submissions found"}

    return {
        "migrated": migrate_count,
        "failed": fail_count,
    }
