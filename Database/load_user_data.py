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


# TO-DO: ADMIN NEEDS TO DETERMINE WHAT LANDMARK ID SHOULD BE FOR EACH LANDMARK. USERS WILL ONLY INPUT A LANDMARK NAME
# THIS MEANS THAT WHEN A USER SUBMITS A LANDMARK, WE NEED TO MAP IT TO THE CORRECT LANDMARK ID IN OUR DATABASE.
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


def fetch_landmark_id(connection, category_name: str):
    """Fetch the landmark_id for a given category_name from the training_data table, or create one"""
    result = connection.execute(
        text("""
        SELECT landmark_id FROM training_data
        WHERE category_name = :category_name
        """),
        {"category_name": category_name},
    ).scalar()
    if result is not None:
        return result
    else:
        new_id = connection.execute(
            text("""
            SELECT COALESCE(MAX(landmark_id), 0) + 1
            FROM training_data""")).scalar()
        return new_id


def move_approved(connection, category_name, landmark_id):
    """Function to move approved submissions to the training_data table"""


# This function can be called at the end of every admin session to push all landmarks that meet he approval threshold
# to the training_data table
# TO-DO: we need logic for generating a new unique id for each row once it is inserted into the training data table
@app.post("/clean")
def clean_tables():
    """Post method for moving entries from user_submission table to training_data table"""
    with engine.begin as connection:
        approved = connection.execute(text("""
            SELECT * FROM user_submissions
            WHERE status = 'approved'
            """)).fetchall()

        for category_name in approved:
            landmark_id = fetch_landmark_id(connection, category_name)

        move_approved(connection, approved)

    return {}  # TO-DO: FIGURE OUT WHAT RETURN SHOULD BE
