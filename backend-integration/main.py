# backend-integration/main.py

"""
TREKMARK BACKEND - main.py

This is the FastAPI backend used by Trekmark.

It sits between the React frontend, the image recognition system, and the Neon
PostgreSQL database.

For the 60% checkpoint, the data flow is:

React uploads image
        ↓
FastAPI /api/predict
        ↓
Simulated ML image recognition
        ↓
landmark_id + confidence
        ↓
Query Neon database
        ↓
Landmark information
        ↓
Other photos of the same landmark
        ↓
Nearby landmarks
        ↓
JSON response to React app

Only the ML image recognition is simulated here. The rest of the data flow is
unchanged.

Once the DINOv2 + FAISS recognition system is ready we will be able to replace
the simulated landmark_id and confidence with the actual values. This will not
require any change to either the backend or frontend data flow.
"""

import os
import secrets
import time
from io import BytesIO
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
from pydantic import BaseModel
import database as database_module

from database import (
    check_database_connection,
    create_user_submission,
    get_landmark,
    get_landmark_photos,
    get_nearby_landmarks,
)


# ENVIRONMENT SETUP
#
# Environmental variables are loaded from backend-integration/.env.
#
# DEMO_MODE is a flag that chooses whether to use simulated image recognition.
#
# DEMO_LANDMARK_ID is the landmark_id returned during the simulated image
# recognition process.
#
# DEMO_CONFIDENCE is the confidence value returned during the simulated image
# recognition process.
#
# These values are configured within the environmental variables in order to
# make it possible to change the demo landmark without touching the python code.

load_dotenv()

DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"

DEMO_LANDMARK_ID = int(
    os.getenv("DEMO_LANDMARK_ID", "104169")
)

DEMO_CONFIDENCE = float(
    os.getenv("DEMO_CONFIDENCE", "0.94")
)


# ADMIN AUTHENTICATION
#
# Admin credentials are kept in .env instead of inside source control.
# The backend creates a short-lived in-memory session token after login.
# Restarting FastAPI clears all admin sessions, which is acceptable for
# the current capstone prototype.
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
ADMIN_SESSION_HOURS = int(os.getenv("ADMIN_SESSION_HOURS", "8"))

if not ADMIN_PASSWORD:
    print("WARNING: ADMIN_PASSWORD is not set. /admin login will be unavailable.")

admin_sessions: dict[str, float] = {}


# FASTAPI SETUP
#
# This code creates the FastAPI application used in Trekmark.
#
# In addition to the code the FastAPI documentation page at /docs will
# automatically show the version, description and title of the FastAPI app.

app = FastAPI(
    title="Trekmark API",
    description="Backend API for Trekmark landmark recognition and trip planning.",
    version="0.6.0",
)


# CORS
#
# CORS is used to allow communication between the FastAPI backend and the React
# app while they are running on different local ports.
#
# React typically runs on local port 5173.
#
# FastAPI typically runs on local port 8000.
#
# Only the local addresses listed are allowed to make browser requests to the API.

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ROOT ENDPOINT
#
# The root endpoint will just return a message that the Trekmark API is up and
# running and will tell you if DEMO_MODE is enabled.

@app.get("/")
def root():
    return {
        "application": "Trekmark API",
        "status": "running",
        "demo_mode": DEMO_MODE,
    }


# HEALTH ENDPOINT
#
# The endpoint /api/health checks that both the FastAPI app is running and the
# Neon connection is working.
#
# The function check_database_connection makes a small query to the Neon database.
#
# If the Neon database responds successfully then the endpoint will return an OK
# response.
#
# If there is an error with the Neon connection then FastAPI will return an HTTP
# 503 response.

@app.get("/api/health")
def health_check():
    try:
        check_database_connection()

        return {
            "api": "ok",
            "database": "ok",
            "demo_mode": DEMO_MODE,
        }

    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"Database connection failed: {error}",
        )


# DIRECT LANDMARK QUERY
#
# There is an endpoint /api/landmark/{landmark_id} which allows for a direct
# query of the landmark using its landmark_id.
#
# The function get_landmark() queries the training_data table in Neon.
#
# If the landmark is not found then FastAPI will return an HTTP 404 error.
#
# This endpoint can be used to test Neon database connectivity independently of
# the image recognition.

@app.get("/api/landmark/{landmark_id}")
def landmark_lookup(landmark_id: int):
    landmark = get_landmark(landmark_id)

    if landmark is None:
        raise HTTPException(
            status_code=404,
            detail=f"Landmark {landmark_id} was not found in Neon.",
        )

    return dict(landmark)


# PREDICTION ENDPOINT
#
# The endpoint /api/predict receives an image from the React app.
#
# The image is sent via multipart/form-data.

@app.post("/api/predict")
async def predict_landmark(
    file: UploadFile = File(...)
):
    # IMAGE CONTENT_TYPE VALIDATION
    #
    # An image content type must be sent. If content type is not image then the
    # request will be rejected with an HTTP 400 error.
    if (
        not file.content_type
        or not file.content_type.startswith("image/")
    ):
        raise HTTPException(
            status_code=400,
            detail="Uploaded file must be an image.",
        )

    # READ IMAGE FROM UPLOAD
    #
    # The image is read into memory using await file.read() and converted into
    # bytes.
    #
    # If no bytes are received then the image is considered to be empty and will
    # be rejected.
    contents = await file.read()

    if not contents:
        raise HTTPException(
            status_code=400,
            detail="Uploaded image is empty.",
        )

    # CHECK IMAGE CONTENT
    #
    # The bytes of the image are passed to Pillow to confirm that they actually
    # represent an image.
    #
    # This is a stronger method of checking than simply verifying content type or
    # extension.
    #
    # If Pillow cannot confirm that the image is valid then FastAPI will return an
    # HTTP 400 error.
    try:
        image = Image.open(BytesIO(contents))
        image.verify()

    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is not a valid image.",
        )

    # TEMPORARY 60% CHECKPOINT ML PREDICTION
    #
    # While DEMO_MODE is enabled Trekmark will use the landmark_id and confidence
    # values from the environmental variables.
    #
    # For the 60% checkpoint this is used to temporarily simulate the DINOv2 +
    # FAISS image recognition.
    #
    # The rest of the system is fully active.
    #
    # This means that the upload from React app, the FastAPI request, the query of
    # Neon, the other photos of the same landmark, the nearby landmarks and the
    # JSON returned to React are all active in the current implementation.
    #
    # This section can be replaced with the actual image recognition
    # implementation as soon as the ML index is ready.
    if DEMO_MODE:
        landmark_id = DEMO_LANDMARK_ID
        confidence = DEMO_CONFIDENCE
        recognition_mode = "demo"

    else:
        raise HTTPException(
            status_code=503,
            detail="Production landmark recognition is not available yet.",
        )

    # REAL NEON QUERY OF A LANDMARK
    #
    # The function get_landmark() will use the landmark_id returned from image
    # recognition to get information about that specific landmark from the
    # training_data table in Neon.
    #
    # If the landmark_id does not exist in Neon then FastAPI will return an HTTP
    # 404 error.
    landmark = get_landmark(landmark_id)

    if landmark is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Prediction returned landmark_id {landmark_id}, "
                "but that landmark does not exist in Neon."
            ),
        )

    # DISPLAY NAME
    #
    # If a value is not present in the name field of the database then the display
    # name will use the following order:
    #
    # 1. name
    # 2. category_name
    # 3. "Landmark {landmark_id}"
    #
    # This ensures that a blank value is never returned to the React app as the
    # display name for a landmark.
    display_name = (
        landmark["name"]
        or landmark["category_name"]
        or f"Landmark {landmark_id}"
    )

    # OTHER PHOTOS OF SAME LANDMARK
    #
    # The function get_landmark_photos() will return photos for the same landmark
    # associated with the landmark_id.
    #
    # Since a landmark_id can exist in more than one row in the training_data table
    # Trekmark is able to show multiple photos of the same landmark.
    #
    # The current implementation only will request up to five photos.
    landmark_photos = get_landmark_photos(
        landmark_id=landmark_id,
        limit=5,
    )

    # NEARBY LANDMARKS
    #
    # Only if the identified landmark has latitude/longitude coordinates will nearby
    # landmarks be calculated.
    #
    # The function get_nearby_landmarks() will return nearby landmarks while
    # excluding the identified landmark.
    #
    # The current implementation will return up to three landmarks within a maximum
    # distance of 600 kilometers.
    #
    # The maximum distance is designed to give recommendations within a specific
    # area or within a reasonable distance of another country.
    nearby_landmarks = []

    if landmark["lat"] is not None and landmark["lon"] is not None:
        nearby_results = get_nearby_landmarks(
            lat=landmark["lat"],
            lon=landmark["lon"],
            exclude_landmark_id=landmark_id,
            limit=3,
            max_distance_km=600.0,
        )

        for nearby in nearby_results:
            # CLEANING NAME OF NEARBY LANDMARK
            #
            # If a value is not present in the name field of the database then the
            # display name will use the following order:
            #
            # 1. name
            # 2. category_name
            # 3. landmark ID
            #
            # If the value category_name is used then the "Category:" text will be
            # removed and any underscores will be replaced with spaces.
            #
            # This is done so that the value is more user friendly.
            nearby_name = (
                nearby["name"]
                or nearby["category_name"]
                or f"Landmark {nearby['landmark_id']}"
            )

            if nearby_name.startswith("Category:"):
                nearby_name = nearby_name.replace(
                    "Category:",
                    ""
                ).replace("_", " ")

            # NEARBY LANDMARKS RESPONSE FORMAT
            #
            # Each nearby landmark is turned into a small JSON object that is
            # friendly to use in the React app.
            #
            # The object contains the following information:
            #
            # - landmark ID
            # - display name
            # - city
            # - state or region
            # - country
            # - image URL
            # - distance in kilometers
            #
            # This information can then be used to create cards for nearby landmarks.
            nearby_landmarks.append({
                "id": nearby["landmark_id"],
                "name": nearby_name,
                "city": nearby["city"],
                "state": nearby["state"],
                "country": nearby["country"],
                "image": nearby["url"],
                "distance_km": float(nearby["distance_km"]),
            })

    # PREDICTION RESPONSE
    #
    # The response to the /api/predict endpoint is a single JSON object that
    # contains all the data the React app needs.
    #
    # This includes:
    #
    # - information about the identified landmark
    # - confidence of the identification
    # - mode of identification
    # - other photos of the same landmark
    # - nearby landmarks
    # - placeholders for future trip planning services
    #
    # The trip_suggestions object already has placeholders for flights, hotels,
    # restaurants, and best time to visit.
    #
    # These can be added later without requiring a complete redesign of the
    # response.
    return {
        "landmark": {
            "id": landmark_id,
            "name": display_name,
            "category_name": landmark["category_name"],
            "city": landmark["city"],
            "state": landmark["state"],
            "country": landmark["country"],
            "latitude": landmark["lat"],
            "longitude": landmark["lon"],
            "image": landmark["url"],
        },

        "confidence": confidence,

        "recognition_mode": recognition_mode,

        "landmark_photos": landmark_photos,

        "nearby_landmarks": nearby_landmarks,

        "trip_suggestions": {
            "flights": [],
            "hotels": [],
            "restaurants": [],
            "best_time_to_visit": None,
        },
    }


# LANDMARK SUBMISSION
#
# The /submission endpoint allows users to submit new landmarks that are not
# currently in Trekmark.
#
# The form for submitting a landmark is sent via the React app using
# multipart/form-data.

@app.post("/submission")
def new_submission(
    # SUBMISSION DATA
    #
    # The following fields are required:
    #
    # - image URL
    # - landmark name
    # - country
    #
    # The following fields are optional:
    #
    # - city
    # - state or region
    # - latitude
    # - longitude
    #
    # Not all landmarks will necessarily have all of these fields. Therefore they
    # are optional.
    #
    # FORM(...)
    #
    # The Form(...) in FastAPI will cause the fields to be read as part of
    # multipart/form-data instead of part of JSON.
    #
    # This is done in order to keep the endpoint open to use in a direct image
    # upload scenario later.
    image_url: str = Form(
        ...,
        description="Image URL for the landmark"
    ),
    name: str = Form(
        ...,
        description="Name of the landmark"
    ),
    country: str = Form(...),
    city: Optional[str] = Form(None),
    state: Optional[str] = Form(None),
    lat: Optional[float] = Form(None),
    lon: Optional[float] = Form(None),
):
    # CLEAN REQUIRED TEXT FIELDS
    #
    # The strip() function will be used to remove any extra spaces at the beginning
    # or end of the required text fields before they are saved.
    image_url = image_url.strip()
    name = name.strip()
    country = country.strip()

    # HANDLE OPTIONAL TEXT FIELDS
    #
    # If the user leaves the city or state field blank then they will be None.
    #
    # This allows the NULL value to be saved to the database instead of an empty or
    # fabricated value.
    city = city.strip() if city else None
    state = state.strip() if state else None

    # VALIDATE REQUIRED FIELDS
    #
    # After cleaning the required text fields another verification step is
    # performed.
    #
    # If any of the image URL, landmark name or country are empty then FastAPI will
    # return an HTTP 400 error.
    if not image_url:
        raise HTTPException(
            status_code=400,
            detail="Image URL is required.",
        )

    if not name:
        raise HTTPException(
            status_code=400,
            detail="Landmark name is required.",
        )

    if not country:
        raise HTTPException(
            status_code=400,
            detail="Country is required.",
        )

    try:
        # SAVE SUBMISSION IN NEON
        #
        # The function create_user_submission() is implemented in database.py.
        #
        # It will insert the data about a user submitted landmark into the
        # user_submissions table in Neon.
        #
        # Right now the image URL submitted by the user will be saved.
        #
        # Once the object storage implementation is complete this can be changed so
        # that the image is uploaded by the backend and the generated object storage
        # URL is saved instead.
        create_user_submission(
            image_url=image_url,
            name=name,
            country=country,
            city=city,
            state=state,
            lat=lat,
            lon=lon,
        )

    except Exception as error:
        # HANDLE DATABASE ERROR WITH SUBMISSION
        #
        # If there is an error during the insert into the database then FastAPI will
        # return an HTTP 500 error with an error message.
        #
        # This ensures that the React app does not indicate a successful submission
        # even if the database insert failed.
        raise HTTPException(
            status_code=500,
            detail=f"Could not save landmark submission: {error}",
        )

    # RESPONSE ON SUCCESSFUL SUBMISSION
    #
    # After the submission is successfully inserted into the database the endpoint
    # will return:
    #
    # status: accepted
    #
    # message: Landmark submitted for review.
    #
    # The React app can use this response to show the success animation and allow
    # the user to enter another landmark.
    return {
        "status": "accepted",
        "message": "Landmark submitted for review.",
    }


# ADMIN API
#
# These routes support the React /admin page. All admin data routes require
# a Bearer token returned by /admin/login.
class AdminLoginRequest(BaseModel):
    username: str
    password: str


class SubmissionInfo(BaseModel):
    name: str
    url: str
    country: str
    city: Optional[str] = None
    state: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    category_name: Optional[str] = None
    landmark_id: Optional[int] = None


def require_admin(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Admin login required.")

    token = authorization.removeprefix("Bearer ").strip()
    expires_at = admin_sessions.get(token)

    if not expires_at or expires_at <= time.time():
        admin_sessions.pop(token, None)
        raise HTTPException(status_code=401, detail="Admin session expired.")

    return token



def get_admin_database_function(name: str):
    function = getattr(database_module, name, None)
    if function is None:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Admin database function '{name}' is not available yet. "
                "Use Chris's updated database.py before using this admin action."
            ),
        )
    return function


@app.post("/admin/login")
def admin_login(credentials: AdminLoginRequest):
    if not ADMIN_PASSWORD:
        raise HTTPException(
            status_code=503,
            detail="ADMIN_PASSWORD has not been configured on the backend.",
        )

    username_ok = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    password_ok = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)

    if not username_ok or not password_ok:
        raise HTTPException(status_code=401, detail="Invalid admin username or password.")

    token = secrets.token_urlsafe(32)
    admin_sessions[token] = time.time() + (ADMIN_SESSION_HOURS * 60 * 60)

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in_hours": ADMIN_SESSION_HOURS,
    }


@app.get("/admin/pending")
def admin_pending(_: str = Depends(require_admin)):
    function = get_admin_database_function("get_pending_submissions")
    return {"submissions": [dict(row) for row in function()]}


@app.get("/admin/non-migrated")
def admin_non_migrated(_: str = Depends(require_admin)):
    function = get_admin_database_function("get_non_migrated_submissions")
    return {"submissions": [dict(row) for row in function()]}


@app.get("/admin/search")
def admin_training_search(name: str, _: str = Depends(require_admin)):
    search_value = name.strip()
    if not search_value:
        return {"results": []}

    function = get_admin_database_function("train_search")
    return {"results": [dict(row) for row in function(search_value)]}


@app.post("/admin/approve/{submission_id}")
def admin_approve_submission(
    submission_id: int,
    info: SubmissionInfo,
    _: str = Depends(require_admin),
):
    function = get_admin_database_function("approve_submission")
    result = function(submission_id, info.model_dump())
    return {
        "status": "approved",
        "message": "Submission approved. It will remain editable until migration.",
        "result": result,
    }


@app.post("/admin/reject/{submission_id}")
def admin_reject_submission(
    submission_id: int,
    _: str = Depends(require_admin),
):
    function = get_admin_database_function("reject_submission")
    result = function(submission_id)
    return {
        "status": "rejected",
        "message": "Submission rejected. The decision can still be changed before migration.",
        "result": result,
    }


@app.put("/admin/submission/{submission_id}")
def admin_update_submission(
    submission_id: int,
    info: SubmissionInfo,
    _: str = Depends(require_admin),
):
    function = get_admin_database_function("update_submission")
    result = function(submission_id, info.model_dump())
    return {
        "status": "updated",
        "message": "Submission changes saved.",
        "result": result,
    }


@app.delete("/admin/submission/{submission_id}")
def admin_delete_submission(
    submission_id: int,
    _: str = Depends(require_admin),
):
    function = get_admin_database_function("delete_submission")
    result = function(submission_id)
    return {
        "status": "deleted",
        "message": "Submission deleted.",
        "result": result,
    }


@app.post("/admin/clean")
def admin_clean_tables(_: str = Depends(require_admin)):
    function = get_admin_database_function("clean_tables")
    result = function()
    return {
        "status": "migrated",
        "message": "Approved submissions were migrated successfully.",
        "result": result,
    }
