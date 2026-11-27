# backend-integration/main.py

"""
TREKMARK BACKEND - main.py

This is the FastAPI backend used by Trekmark.

It sits between the React frontend, the image recognition system, and the Neon
PostgreSQL database.

The recognition data flow is:

React uploads image
        ↓
FastAPI /api/predict
        ↓
DINOv2 embeddings + FAISS nearest-neighbor search
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

Real recognition uses the supplied DINOv2 model and FAISS index. Demo mode can
be enabled explicitly for testing. Accounts, uploads, admin, airports, hotels
and restaurants use the same routes in either mode.
"""

import os
import secrets
import time
import inspect
import logging
import math
from io import BytesIO
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from starlette.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from PIL import Image
from pydantic import BaseModel, field_validator

# Load this backend's settings before database.py creates its engine.
load_dotenv(Path(__file__).resolve().with_name(".env.ml"))
load_dotenv(Path(__file__).resolve().with_name(".env"))

from hotels_service import get_hotels
from restaurants_service import get_restaurants
from airports_service import get_nearest_airport
from ml_service import recognize_image, MLConfigurationError
from featured_service import get_featured_destination, FeaturedUnavailable
from category_format import format_category_name
from accounts_api import router as accounts_router, allowed_origins, rate_limit, store_image, discard_image

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

# The .env file is loaded above before importing the database module.

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
    allow_origins=allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(accounts_router)

@app.exception_handler(RequestValidationError)
async def readable_validation_error(request: Request, error: RequestValidationError):
    # Return field names and messages, never raw passwords or uploaded bytes.
    labels = {"image": "Landmark photo", "file": "Image file", "name": "Landmark name",
              "country": "Country", "lat": "Latitude", "lon": "Longitude",
              "email": "Email", "password": "Password", "username": "Username"}
    errors = []
    for item in error.errors():
        location = item.get("loc", ())
        field = str(location[-1]) if location else "request"
        label = labels.get(field, field.replace("_", " ").capitalize())
        message = "This field is required." if item.get("type") == "missing" else item.get("msg", "Check this value.")
        errors.append({"field": field, "message": f"{label}: {message}"})
    logging.getLogger("uvicorn.error").warning("Validation rejected %s: %s", request.url.path, " ".join(item["message"] for item in errors))
    return JSONResponse(status_code=422, content={
        "detail": " ".join(item["message"] for item in errors), "errors": errors})


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


@app.get("/api/featured/{preset_id}")
def featured_destination(preset_id: str):
    # Curated picks use Neon IDs, photos and coordinates without an ML upload.
    try:
        search = getattr(database_module, "train_search", None)
        if search is None:
            raise HTTPException(503, "Featured landmark search is unavailable. Check database.py.")
        return get_featured_destination(preset_id, search, get_landmark,
                                        get_landmark_photos, get_nearby_landmarks)
    except FeaturedUnavailable as error:
        raise HTTPException(404, str(error))
    except HTTPException:
        raise
    except Exception:
        logging.exception("Featured destination lookup failed")
        raise HTTPException(503, "The featured destination could not be loaded. Please try again.")


# PREDICTION ENDPOINT
#
# The endpoint /api/predict receives an image from the React app.
#
# The image is sent via multipart/form-data.

# Keep the backend cutoff aligned with the frontend's additional upload guard.
# Backend unknown/rejected outcomes remain authoritative at any score.
MIN_RECOGNITION_SCORE = 0.25


def normalize_recognition_result(result):
    """Accept both ML response versions without inventing calibrated certainty."""
    if not isinstance(result, dict):
        raise MLConfigurationError("The recognition service returned an invalid result.")

    def valid_score(value):
        return (isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(value) and 0 <= value <= 1)

    # The older ML service calls its raw similarity 'confidence'.
    raw_score = result.get("match_score")
    if raw_score is None:
        raw_score = result.get("confidence")
    if raw_score is None:
        raw_score = result.get("similarity")
    raw_score = float(raw_score) if valid_score(raw_score) else None

    probability = result.get("confidence_probability")
    calibrated = result.get("confidence_calibrated") is True and valid_score(probability)
    probability = float(probability) if calibrated else None
    score = probability if calibrated else raw_score

    return {
        **result,
        "match_score": raw_score,
        "confidence_probability": probability,
        "confidence_calibrated": calibrated,
        "confidence": score,
    }


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
    contents = await file.read(10 * 1024 * 1024 + 1)
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(413, "Choose an image smaller than 10 MB.")

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

    # Real recognition runs off the event loop and returns a Neon landmark ID.
    # DEMO_MODE remains an explicit fallback for presentation/testing only.
    ml_result = None
    if DEMO_MODE:
        landmark_id = DEMO_LANDMARK_ID
        confidence = DEMO_CONFIDENCE
        recognition_mode = "demo"

    else:
        try:
            ml_result = normalize_recognition_result(
                await run_in_threadpool(recognize_image, contents)
            )
            # A rejected candidate is a normal recognition outcome. Do not look
            # up its ID in Neon or search travel services for an uncertain place.
            if (ml_result.get("prediction_status") == "unknown"
                    or ml_result.get("landmark_id") is None
                    or ml_result["confidence"] is None
                    or ml_result["confidence"] < MIN_RECOGNITION_SCORE):
                return {
                    "prediction_status": "unknown", "recognition_mode": "ml",
                    "message": "We couldn’t identify this landmark reliably. Try a clearer photo with the landmark filling more of the frame, or explore a featured destination.",
                    "landmark": None, "confidence": None, "confidence_probability": None,
                    "confidence_calibrated": False,
                    "confidence_description": ml_result.get("confidence_description"),
                    "match_score": ml_result.get("match_score"), "match_details": ml_result,
                    "landmark_photos": [], "nearby_landmarks": [],
                    "trip_suggestions": {"flights": [], "hotels": [], "restaurants": [],
                                         "hotel_search": None, "restaurant_search": None,
                                         "best_time_to_visit": None},
                }
            landmark_id = int(ml_result["landmark_id"])
            confidence = ml_result["confidence"]
            recognition_mode = "ml"
        except MLConfigurationError as error:
            logging.exception("ML recognition could not load")
            raise HTTPException(503, detail=str(error))
        except ValueError as error:
            raise HTTPException(422, detail=str(error))
        except Exception:
            logging.exception("ML recognition failed")
            raise HTTPException(503, "Recognition could not finish. Check the backend terminal and try again.")

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

    # Nearby recommendations are optional: a helper mismatch must never
    # turn a valid image upload into HTTP 500.
    try:
        if landmark["lat"] is not None and landmark["lon"] is not None:
            # Branches currently have different database helper signatures. Pass
            # only supported keywords; validate before calling, so we never retry
            # a database operation after an internal TypeError.
            candidates = {
                "lat": landmark["lat"], "lon": landmark["lon"],
                "exclude_landmark_id": landmark_id, "landmark_id": landmark_id, "limit": 4,
                "max_distance_km": 600.0,
            }
            signature = inspect.signature(get_nearby_landmarks)
            accepts_kwargs = any(
                parameter.kind == inspect.Parameter.VAR_KEYWORD
                for parameter in signature.parameters.values()
            )
            arguments = {
                key: value for key, value in candidates.items()
                if accepts_kwargs or key in signature.parameters
            }
            signature.bind(**arguments)
            nearby_results = get_nearby_landmarks(**arguments)

            for nearby in nearby_results:
                # Exclude the recognized landmark even when the database helper
                # has no exclusion argument. Keep at most three recommendations.
                if str(nearby["landmark_id"]) == str(landmark_id):
                    continue
                if len(nearby_landmarks) >= 3:
                    break
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

    except Exception:
        logging.getLogger(__name__).exception(
            "Nearby landmark lookup failed; returning recognition and hotels."
        )
        nearby_landmarks = []

    # AUTOMATIC HOTEL SEARCH
    #
    # Use the coordinates retrieved from Neon, not hardcoded frontend values.
    # Hotel failure returns an unavailable state instead of losing the landmark.
    # The network request runs in a worker thread so it does not block FastAPI's
    # event loop. Future ML predictions use this same database-to-hotel flow.
    hotel_search = await run_in_threadpool(
        get_hotels, landmark["lat"], landmark["lon"], 5000, 3
    )

    # Restaurants use the same Neon coordinates, automatically after hotels.
    # Keeping the calls sequential also respects Wikimedia's request policy.
    restaurant_search = await run_in_threadpool(
        get_restaurants, landmark["lat"], landmark["lon"], 5000, 3
    )

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
    # - nearby hotels and their provider status
    # - placeholders for remaining trip planning services
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
        "confidence_calibrated": bool(ml_result and ml_result.get("confidence_calibrated")),
        "confidence_probability": ml_result.get("confidence_probability") if ml_result else None,
        "match_score": ml_result.get("match_score") if ml_result else None,
        "confidence_description": ml_result.get("confidence_description") if ml_result else "Preset demonstration score; not calibrated.",
        "prediction_status": ml_result.get("prediction_status") if ml_result else "demo",
        "match_details": ml_result,

        "recognition_mode": recognition_mode,

        "landmark_photos": landmark_photos,

        "nearby_landmarks": nearby_landmarks,

        "trip_suggestions": {
            "flights": [],
            "hotels": hotel_search["hotels"],
            "hotel_search": hotel_search,
            "restaurants": restaurant_search["restaurants"],
            "restaurant_search": restaurant_search,
            "best_time_to_visit": None,
        },
    }


# DIRECT HOTEL SEARCH
#
# Used by preset destinations, radius changes and retries in the frontend.
# Uploaded landmarks receive their first search automatically in /api/predict.
@app.get("/api/hotels")
def hotels(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_m: int = Query(5000, ge=500, le=25000),
    limit: int = Query(3, ge=1, le=3),
):
    result = get_hotels(lat, lon, radius_m, limit)
    if result["status"] != "ok":
        status_code = {
            "missing_coordinates": 422,
            "invalid_search": 422,
            "not_configured": 503,
            "authentication_error": 503,
            "quota_reached": 503,
            "timeout": 504,
        }.get(result["status"], 502)
        raise HTTPException(status_code=status_code, detail=result["message"])
    return result


# Preset destinations and radius changes use the same automatic lookup.
@app.get("/api/restaurants")
def restaurants(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_m: int = Query(5000, ge=500, le=25000),
    limit: int = Query(3, ge=1, le=3),
):
    result = get_restaurants(lat, lon, radius_m, limit)
    if result["status"] != "ok":
        status_code = {
            "missing_coordinates": 422, "invalid_search": 422,
            "not_configured": 503, "authentication_error": 503,
            "quota_reached": 503, "timeout": 504,
        }.get(result["status"], 502)
        raise HTTPException(status_code=status_code, detail=result["message"])
    return result


# The frontend starts this lookup automatically when a destination is selected.
# It runs independently so airport lookup never delays image recognition.
@app.get("/api/airports")
def airports(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    international_only: bool = Query(False),
):
    result = get_nearest_airport(lat, lon, international_only)
    if result["status"] != "ok":
        status_code = {
            "missing_coordinates": 422, "invalid_search": 422,
            "not_configured": 503, "authentication_error": 503,
            "quota_reached": 503, "timeout": 504,
        }.get(result["status"], 502)
        raise HTTPException(status_code=status_code, detail=result["message"])
    return result


# LANDMARK SUBMISSION
#
# The /submission endpoint allows users to submit new landmarks that are not
# currently in Trekmark.
#
# The form for submitting a landmark is sent via the React app using
# multipart/form-data.

@app.post("/submission")
def new_submission(
    request: Request,
    image: UploadFile = File(...),
    name: str = Form(...),
    country: str = Form(...),
    city: Optional[str] = Form(None),
    state: Optional[str] = Form(None),
    lat: Optional[str] = Form(None),
    lon: Optional[str] = Form(None),
):
    # Read a bounded file; never trust the filename or declared MIME type.
    rate_limit(request, "submission", 15)
    name, country = name.strip(), country.strip()
    # Optional coordinate inputs may arrive as blank strings in multipart forms.
    def coordinate(value, label, bound):
        if value is None or not value.strip():
            return None
        try:
            number = float(value.strip())
            if not math.isfinite(number) or abs(number) > bound:
                raise ValueError()
            return number
        except (ValueError, TypeError):
            raise HTTPException(422, f"{label} must be a number between -{bound} and {bound}, or left blank.")
    lat, lon = coordinate(lat, "Latitude", 90), coordinate(lon, "Longitude", 180)
    if not name or not country or len(name) > 200 or len(country) > 120:
        raise HTTPException(422, "Enter a landmark name and country (200/120 characters maximum).")
    content = image.file.read(10 * 1024 * 1024 + 1)
    image_id = None
    try:
        image_id = store_image(content)
        image_url = str(request.url_for("landmark_media", image_id=image_id))
        submission_id = create_user_submission(image_url=image_url, name=name, country=country,
            city=city.strip() if city else None, state=state.strip() if state else None, lat=lat, lon=lon)
    except HTTPException:
        raise
    except Exception:
        if image_id:
            try:
                discard_image(image_id)
            except Exception:
                logging.exception("Could not remove failed submission image")
        logging.exception("Could not save landmark submission")
        raise HTTPException(503, "The landmark could not be saved. Please try again.")
    finally:
        image.file.close()
    return {"status": "accepted", "message": "Landmark submitted for review.",
            "submission_id": submission_id, "image_url": image_url}


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

    @field_validator("category_name", mode="before")
    @classmethod
    def normalize_category(cls, value):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Category must be text.")
        formatted = format_category_name(value)
        if formatted and len(formatted) > 250:
            raise ValueError("Category must be at most 250 characters.")
        return formatted


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
def admin_login(credentials: AdminLoginRequest, request: Request):
    rate_limit(request, "admin_login", 10)
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
    if not info.category_name:
        raise HTTPException(422, "Enter a category before approving this landmark.")
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
