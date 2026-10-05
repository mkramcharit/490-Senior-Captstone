# Three goals for this code:
# 1. The user needs to be able to submit landmarks to be added to the database
# 2. The admins need to be able to review landmarks and either reject or approve them
# 3. Once we have enough (30) approved images for a landmark in our holding table,
#    we want to move all the related rows from the holding table to the actual training_data table

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import boto3
import os
import uuid

load_dotenv()

BUCKET_NAME = "image-bucket"
BASE_URL = os.environ["ENDPOINT_URL_S3"] + "/" + BUCKET_NAME
# THRESHOLD = 30 # We will use this later if we want to

app = FastAPI(title="Ladmark Submission API")
engine = create_engine(os.environ["DATABASE_URL"])  # Neon connection object

client = boto3.client(
    "s3",
    region=os.environ["REGION"],
    endpoint_url_s3=os.environ["ENDPOINT_URL_S3"],
    token_id=os.environ["TOKEN_ID"],
    s3_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
)


class SubmissionInfo(BaseModel):
    category_name: str
    lat: float
    lon: float
    city: str | None = None
    state: str | None = None
    country: str | None = None


def upload_image(image: UploadFile):
    """Function to upload image to S3 bucket"""
    extension = image.filename.split(".")[-1] if "." in image.filename else "jpg"

    key = f"{uuid.uuid4().hex}{extension}"
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
        connection.execute(text("""
        INSERT INTO user_submissions (url, name, lat, lon, city, state, country)
        VALUES (:url, :name, :lat, :lon, :city, :state, :country)"""))

    return "Accepted"


# Make sure in front end that admin inputs a category_name
@app.post("/submissions/approve/{submission_id}")
def approve_submission(submission_id: int, info: SubmissionInfo):
    """Post for admin approving a submission"""
    with engine.begin() as connection:
        result = connection.execute(
            text("""
            UPDATE user_submissions
            SET status = 'approved',
            WHERE submission_id = :submission_id"""),
            {
                "submission_id": submission_id,
                "category_name": info.category_name,
                "lat": info.lat,
                "lon": info.lon,
                "city": info.city,
                "state": info.state,
                "country": info.country,
            },
        )

    if result.rowcount == 0:
        raise HTTPException(404, detail="Error: No matching item")

    return {"message": "Submission approved"}


@app.post("/admin/reject/{submission_id}")
def reject_submission(submission_id: int):
    """Post for when admin rejects a submission"""
    with engine.begin() as connection:
        result = connection.execute(
            text("""
            UPDATE user_submissions
            SET status = 'rejected',
            WHERE submission_id = :submission_id"""),
        )

    if result.rowcount == 0:
        raise HTTPException(404, detail="Error: No matching item")

    return {"message": "Submission rejected"}


def get_approved(connection):
    """Fetch all approved submissions from the user_submissions table"""
    approved = connection.execute(text("""
        SELECT * FROM user_submissions
        WHERE status = 'approved'
    """))
    return approved


def fetch_landmark_id(connection, category_name: str):
    """Fetch the landmark_id for a given category_name from the training_data table, or create one"""
    result = connection.execute(
        text("""
        SELECT landmark_id FROM training_data
        WHERE category_name = :category_name 
        LIMIT 1
        """),
        {"category_name": category_name},
    ).scalar()
    if result is not None:
        return result
    else:
        new_id = connection.execute(text("""
            SELECT COALESCE(MAX(landmark_id), 0) + 1
            FROM training_data""")).scalar()
        return new_id


def move_approved(connection, landmark_id, submission):
    """Function to move approved submissions to the training_data table"""
    connection.execute(
        text("""
        INSERT INTO training_data (id, url, landmark_id, category_name, name, lat, lon, country, city, state)
        VALUES (:id, :url, :landmark_id, :category_name, :name, :lat, :lon, :country, :city, :state)
        """),
        {
            "id": uuid.uuid4().hex[:16],
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

    connection.execute(  # mark the submission as migrated
        text("""
        UPDATE user_submissions
        SET status = 'migrated'
        WHERE submission_id = :submission_id
        """),
        {"submission_id": submission.submission_id},
    )


# This function can be called at the end of every admin session
@app.post("/clean")
def clean_tables():
    """Post method for moving entries from user_submission table to training_data table"""

    migrate_count = 0
    with engine.begin() as connection:
        approved_submission = get_approved(connection)

        for submission in approved_submission:
            new_landmark_id = fetch_landmark_id(connection, submission.category_name)
            move_approved(connection, new_landmark_id, submission)
            migrate_count += 1

        if migrate_count == 0:
            return {"message": "no approved submissions found"}

    return {"message": f"successfully migrated {migrate_count} submissions"}
