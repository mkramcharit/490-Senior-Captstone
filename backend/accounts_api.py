# PERSISTENT ACCOUNTS, SAVED TRIPS, AND IMAGE STORAGE
# Support for persistent user accounts, private saved trips, and image storage.
# 
# This module will only create Trekmark-owned tables in the current database upon first
# use.
# The default image storage is Neon binary. To use a private S3-compatible image storage,
# set IMAGE_STORAGE=s3 and S3_BUCKET, S3_ENDPOINT_URL (optional if using AWS),
# AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and AWS_DEFAULT_REGION.
# All image URLs will route to the backend and the keys for the private S3 bucket will be
# hidden.


# IMPORTS
# Support for password verification and session tokens via hashing, HMAC and secrets.
# Use UUIDs to identify records and time records for date of creation, expiry, and rate-
# limiting.
# Support for thread safe initialization and attempt tracking using threading and
# OrderedDict.
# Use FastAPI to provide routing, dependencies, responses, and requests.
# Use Pydantic to validate request content.
# Use SQLAlchemy to create and query tables.
# Use Pillow to decode, validate, rotate, resize, and convert images uploaded to the
# service.
import hashlib

import hmac

import io

import json

import logging

import math

import os

import re

import secrets

import threading

import time

import uuid

from collections import OrderedDict



from fastapi import APIRouter, Depends, HTTPException, Request, Response

from pydantic import BaseModel, Field

from sqlalchemy import (MetaData, Table, Column, String, Text, Float, LargeBinary,

                        ForeignKey, UniqueConstraint, select, insert, update, delete)

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from PIL import Image, ImageOps, UnidentifiedImageError



# ROUTER AND TABLE METADATA
# This module is registered as a collection of endpoints in the main FastAPI application
# via APIRouter.
# There are four Trekmark-owned tables as defined by a MetaData object.
# Creation of these tables will not recreate existing training or landmark tables.
router = APIRouter()

metadata = MetaData()

# USER TABLE
# Create a record with user id (UUID), email, display_name, password hash, and
# creation_date.
# Passwords are hashed with a random salt using password hash rather than storing
# passwords in plain text.
users = Table('trekmark_users', metadata,

    Column('id', String(36), primary_key=True), Column('email', String(254), nullable=False, unique=True),

    Column('display_name', String(80), nullable=False), Column('password_hash', Text, nullable=False),

    Column('created_at', Float, nullable=False))

# SESSION TABLE
# Create a record with user_id, token hash, and expiry.
# Set the foreign key on user to cascade deletion.
# Index user_id and expiry.
# Token is not stored in the database, but the token hash is. The token is sent to the
# browser.
sessions = Table('trekmark_sessions', metadata,

    Column('token_hash', String(64), primary_key=True),

    Column('user_id', String(36), ForeignKey('trekmark_users.id', ondelete='CASCADE'), nullable=False, index=True),

    Column('expires_at', Float, nullable=False, index=True))

# SAVED-TRIP TABLE
# Create a record with saved_trip_id, user_id, destination_key, title, and JSON snapshot
# along with timestamps.
# For each user and destination there can be only one record created by the user for that
# destination. Each user can create a record for the same destination separately.
# The foreign key on user is set to cascade on deletion.
favorites = Table('trekmark_favorites', metadata,

    Column('id', String(36), primary_key=True),

    Column('user_id', String(36), ForeignKey('trekmark_users.id', ondelete='CASCADE'), nullable=False, index=True),

    Column('destination_key', String(64), nullable=False), Column('title', String(120), nullable=False),

    Column('snapshot', Text, nullable=False), Column('created_at', Float, nullable=False),

    Column('updated_at', Float, nullable=False), UniqueConstraint('user_id', 'destination_key'))

# IMAGE TABLE
# Create a record with image_id, creation_date, and storage.
# When storing in database, store the image as a JPEG in the data column. When storing in
# s3, store the s3 object key.
# There is no user foreign key on this table. This is intended for storage of images from
# landmarks.
images = Table('trekmark_images', metadata,

    Column('id', String(36), primary_key=True), Column('data', LargeBinary),

    Column('object_key', String(200)), Column('storage', String(16), nullable=False),

    Column('created_at', Float, nullable=False))

# COOKIE AND SESSION LIFETIME
# The session cookie should be named trekmark_session.
# SESSION_SECONDS is thirty days. This is not related to admin bearer tokens.
COOKIE = 'trekmark_session'

SESSION_SECONDS = 30 * 86400

# SHARED STORE AND LOCKS
# _store holds a shared Store object in the current Python process.
# _store_lock prevents multiple threads from trying to initialize the Store object at the
# same time.
# _attempts and _attempt_lock provide synchronized access to per-process rate limiting.
_store = None

_store_lock = threading.Lock()

_attempts = OrderedDict()

_attempt_lock = threading.Lock()





# INITIALIZE STORAGE
# The Store object stores the existing database engine and calls metadata.create_all().
# This will create any tables that are declared but not yet present in the database. This
# is not a tool for migrating existing tables by changing columns or constraints on
# existing tables.
class Store:

    def __init__(self, engine):

        self.engine = engine

        metadata.create_all(engine)





# GET THE SHARED STORE
# The get_store() function will lazily initialize a Store object using the database engine
# from the database.py module.
# After the lock is acquired, a second check is made to see if the initialized Store
# object is already present to allow for multiple threads to reuse an already initialized
# Store.
# If the engine import or creation of tables fails in one of the handled ways, log the
# failure and return a 503 HTTP error.
def get_store():

    global _store

    if _store is None:

        with _store_lock:

            if _store is None:

                try:

                    from database import engine

                    _store = Store(engine)

                except (ImportError, AttributeError, SQLAlchemyError):

                    logging.exception('Account tables could not be initialized')

                    raise HTTPException(503, 'Account storage is unavailable. Check the database connection and table creation permissions.')

    return _store





# ALLOWED FRONTEND ORIGINS
# Read FRONTEND_ORIGINS as a comma delimited list and strip any extra spaces or trailing
# slashes.
# Use localhost and 127.0.0.1 on port 5173 as default.
def allowed_origins():

    return [origin.strip().rstrip('/') for origin in os.getenv(

        'FRONTEND_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(',') if origin.strip()]





# PROTECT WRITE REQUESTS
# Require a custom header to force CORS preflight and check the origin of the request.
# Require X-Trekmark-Request: 1 and, if an Origin header is present, require it to match
# one of the allowed origins.
# If the required custom header is present, an Origin header is not required.
# If the required custom header is present, CORS preflight will only be triggered on
# cross-origin requests. Same-origin requests will not trigger a preflight. The main
# FastAPI application must configure CORS independently.
# This is not a substitute for session authentication on protected routes.
def protect_write(request: Request):


    origin = request.headers.get('origin')

    if request.headers.get('x-trekmark-request') != '1' or (origin and origin.rstrip('/') not in allowed_origins()):

        raise HTTPException(403, 'This request must come from the Trekmark site.')





# RATE LIMITING
# Track the number of attempts by host and action within a five minute time window.
# Default is ten attempts per window. Registration has a rate limit of five.
# Return HTTP 429 when the number of attempts reaches the limit.
# Only store 4096 entries and remove the least recently used entries.
# This counter is per-process and will be reset on restart.
def rate_limit(request, action, allowance=10):

    key = (request.client.host if request.client else 'unknown', action)

    now = time.monotonic()

    with _attempt_lock:

        entry = _attempts.get(key)

        count, expires = entry if entry and entry[1] > now else (0, now + 300)

        if count >= allowance:

            raise HTTPException(429, 'Too many attempts. Please wait five minutes.')

        _attempts[key] = (count + 1, expires)

        _attempts.move_to_end(key)

        while len(_attempts) > 4096:

            _attempts.popitem(last=False)





# HASH PASSWORDS
# Generate a random 16 byte salt and store it as hexadecimal text.
# Generate the hash using PBKDF2-HMAC-SHA256 with 600000 iterations.
# Store the algorithm, iterations, salt, and digest as a single string.
def hash_password(password):

    salt = secrets.token_hex(16)

    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex()

    return f'pbkdf2_sha256$600000${salt}${digest}'





# VERIFY PASSWORDS
# Parse the stored string and ensure the expected algorithm and iterations are present.
# Generate a hash from the stored salt and password.
# Compare the digests using hmac.compare_digest(). Return False if malformed values are
# encountered and handled.
def verify_password(password, stored):

    try:

        algorithm, iterations, salt, digest = stored.split('$')

        if algorithm != 'pbkdf2_sha256' or int(iterations) != 600000:

            return False

        expected = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(iterations)).hex()

        return hmac.compare_digest(digest, expected)

    except (ValueError, TypeError):

        return False





# PUBLIC USER RESPONSE
# Only return the id, email, and display_name. Do not return password hashes or sessions.
def public_user(row):

    return {'id': row['id'], 'email': row['email'], 'display_name': row['display_name']}





# CREATE A SESSION
# Generate a random URL-safe token. Remove expired sessions. Create a new session with a
# SHA256 hash of the new token, user_id, and thirty day expiry. Save this session within a
# transaction.
# Set the token as an HttpOnly cookie with SameSite=Lax and path=/ .
# Enable the Secure cookie flag if the request is made over HTTPS or if
# SESSION_COOKIE_SECURE=true.
# Set no-store on the response to prevent responses to account/session data from being
# cached.
def new_session(user_id, request, response, store):

    token = secrets.token_urlsafe(32)

    now = time.time()

    with store.engine.begin() as connection:

        connection.execute(delete(sessions).where(sessions.c.expires_at <= now))

        connection.execute(insert(sessions).values(token_hash=hashlib.sha256(token.encode()).hexdigest(), user_id=user_id, expires_at=now + SESSION_SECONDS))

    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True,

        secure=request.url.scheme == 'https' or os.getenv('SESSION_COOKIE_SECURE', '').lower() == 'true',

        samesite='lax', path='/')

    response.headers['Cache-Control'] = 'no-store'





# RESOLVE THE CURRENT USER
# Read the session cookie and return a 401 if the cookie is not present.
# Hash the token and join the user and session tables to find a match for the unexpired
# session.
# Return 401 if no matching session is found. If a matching session is found return the
# public user data.
# This service is used to resolve the user information required to scope saved trips.
def current_user(request: Request):

    token = request.cookies.get(COOKIE)

    if not token:

        raise HTTPException(401, 'Sign in to view and save your trips.')

    store = get_store()

    with store.engine.connect() as connection:

        row = connection.execute(select(users).join(sessions, users.c.id == sessions.c.user_id).where(

            sessions.c.token_hash == hashlib.sha256(token.encode()).hexdigest(), sessions.c.expires_at > time.time())).mappings().first()

    if not row:

        raise HTTPException(401, 'Your session expired. Please sign in again.')

    return public_user(row)





# CREDENTIAL REQUEST MODELS
# Credentials model checks the email and password string length.
# During registration a display_name field of one to eighty characters is required.
# Password must also be at least ten characters long during registration.
class Credentials(BaseModel):

    email: str = Field(min_length=3, max_length=254)

    password: str = Field(min_length=1, max_length=128)





class Registration(Credentials):

    display_name: str = Field(min_length=1, max_length=80)





# NORMALIZE EMAIL
# Strip the email and apply casefold() before use in lookups and storage.
# The intended regular expression just ensures that the email is in the expected format
# for an email.
# The regular expression checks for text around an @ sign and a dot in the domain.
# This does not verify ownership of an email address.
def normalized_email(value):

    value = value.strip().casefold()

    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):

        raise HTTPException(422, 'Enter a valid email address.')

    return value





# REGISTER A TRAVELER
# Protect write requests, limit registration by rate limiting, normalize the email and
# strip the display name.
# Reject a blank display name or a short password with HTTP 422.
# Create a UUID and a password hash and insert the traveler into the database within a
# transaction.
# Return 409 for any handled integrity constraints such as a duplicate email address.
# Create a session after account creation and return the public account information.
@router.post('/api/auth/register', dependencies=[Depends(protect_write)])

def register(body: Registration, request: Request, response: Response):

    rate_limit(request, 'register', 5)

    email = normalized_email(body.email)

    name = body.display_name.strip()

    if not name or len(body.password) < 10:

        raise HTTPException(422, 'Enter your name and use a password with at least 10 characters.')

    store = get_store()

    row = {'id': str(uuid.uuid4()), 'email': email, 'display_name': name,

           'password_hash': hash_password(body.password), 'created_at': time.time()}

    try:

        with store.engine.begin() as connection:

            connection.execute(insert(users).values(**row))

    except IntegrityError:

        raise HTTPException(409, 'An account already uses that email. Sign in instead.')

    new_session(row['id'], request, response, store)

    return {'user': public_user(row)}





# TRAVELER LOGIN
# Protect and rate limit the request. Normalize the email and get the user.
# Perform the same password matching as for a non-existing user.
# If no user exists use a dummy PBKDF2 password hash format so a non-existing user does
# also have to perform password derivation. This does not mean that the time to perform
# this will be identical for a non-existing user and a matching user.
# Return a generic 401 error if a password is invalid or a user is not found.
# Upon success, create a session and return the public account information.
@router.post('/api/auth/login', dependencies=[Depends(protect_write)])

def login(body: Credentials, request: Request, response: Response):

    rate_limit(request, 'login')

    store = get_store()

    email = normalized_email(body.email)

    with store.engine.connect() as connection:

        row = connection.execute(select(users).where(users.c.email == email)).mappings().first()


    stored = row['password_hash'] if row else 'pbkdf2_sha256$600000$' + '00' * 16 + '$' + '00' * 32

    if not verify_password(body.password, stored) or not row:

        raise HTTPException(401, 'The email or password is incorrect.')

    new_session(row['id'], request, response, store)

    return {'user': public_user(row)}





# CURRENT ACCOUNT ENDPOINT
# GET /api/auth/me requires current_user and returns the current user.
# Set Cache-Control: no-store on the returned response.
@router.get('/api/auth/me')

def me(response: Response, user=Depends(current_user)):

    response.headers['Cache-Control'] = 'no-store'

    return {'user': user}





# TRAVELER LOGOUT
# Protect the request. If the request contains a token delete the session matching the
# hash of the token. Then remove the cookie and return status ok.
# This does not delete the account or saved trips.
@router.post('/api/auth/logout', dependencies=[Depends(protect_write)])

def logout(request: Request, response: Response):

    token = request.cookies.get(COOKIE)

    if token:

        with get_store().engine.begin() as connection:

            connection.execute(delete(sessions).where(sessions.c.token_hash == hashlib.sha256(token.encode()).hexdigest()))

    response.delete_cookie(COOKIE, path='/')

    response.headers['Cache-Control'] = 'no-store'

    return {'status': 'ok'}





# SAVED-TRIP REQUEST MODEL
# FavoriteBody requires a destination and a title of one to 120 characters.
# When saving a favorite the title must be non-empty after trimming.
class FavoriteBody(BaseModel):

    destination: dict

    title: str = Field(min_length=1, max_length=120)





# VALIDATE A DESTINATION SNAPSHOT
# Require a non-empty destination name.
# Require lat and lng to be convertable to finite numbers within plus or minus 90 and 180
# respectively. These validations do not modify the lat/lng values stored in the
# destination object.
# The destination must be serializable to JSON with all non-ASCII characters intact and
# NaN values not allowed. Invalid payloads or JSON values over 250000 bytes are rejected.
def clean_snapshot(destination):

    if not isinstance(destination.get('name'), str) or not destination['name'].strip():

        raise HTTPException(422, 'Choose a destination before saving your trip.')

    for key, bound in [('lat', 90), ('lng', 180)]:

        try:

            value = destination[key]

            if value is None or value == '' or not math.isfinite(float(value)) or abs(float(value)) > bound:

                raise ValueError()

        except (KeyError, ValueError, TypeError):

            raise HTTPException(422, 'This trip needs valid destination coordinates.')

    try:

        payload = json.dumps(destination, allow_nan=False, ensure_ascii=False)

    except (ValueError, TypeError):

        raise HTTPException(422, 'The trip could not be saved. Select the destination again.')

    if len(payload.encode()) > 250000:

        raise HTTPException(413, 'This trip is too large to save.')

    # DESTINATION IDENTITY
    # Try landmarkId first, then id, then the tuple of name, latitude, and longitude.
    # Convert this to text and create a SHA256 hash of this to be the destination key.
    # Return the serialized destination snapshot and destination key. The destination key
    # is not for every single change made to a saved trip but rather is a key for the
    # destination.
    identity = str(destination.get('landmarkId') or destination.get('id') or (destination['name'], destination['lat'], destination['lng']))

    return payload, hashlib.sha256(identity.encode()).hexdigest()





# LIST PRIVATE SAVED TRIPS
# GET /api/favorites requires current_user and only queries records for that user.
# Sort the records by updated_at in descending order and decode the JSON snapshot.
# Return the ID, title, destination, and timestamps with no-store on the response.
@router.get('/api/favorites')

def list_favorites(response: Response, user=Depends(current_user)):

    response.headers['Cache-Control'] = 'no-store'

    with get_store().engine.connect() as connection:

        rows = connection.execute(select(favorites).where(favorites.c.user_id == user['id']).order_by(favorites.c.updated_at.desc())).mappings().all()

    return {'favorites': [{'id': row['id'], 'title': row['title'], 'destination': json.loads(row['snapshot']),

            'created_at': row['created_at'], 'updated_at': row['updated_at']} for row in rows]}





# SAVE OR UPDATE A PRIVATE TRIP
# POST /api/favorites requires current_user and write protection.
# Validate the destination snapshot and create a destination key based on the snapshot.
# Reject a blank title after trimming.
# Because of the unique combination of user and destination the same record can be updated
# on a repeat save.
# Within a transaction query for a record with the same user and destination. If a record
# is found update the title, snapshot, and updated_at while maintaining the existing ID.
# If no record is found create a new record with a UUID and creation and updated_at
# values.
# Return a 409 if a conflict is found and there is an integrity constraint violation
# caught as a conflicting insert.
# Return the ID of the created or updated record after a successful transaction.
@router.post('/api/favorites', dependencies=[Depends(protect_write)])

def save_favorite(body: FavoriteBody, user=Depends(current_user)):

    payload, identity = clean_snapshot(body.destination)

    title = body.title.strip()

    if not title:

        raise HTTPException(422, 'Give your saved trip a name.')

    store = get_store()

    now = time.time()


    try:

        with store.engine.begin() as connection:

            existing = connection.execute(select(favorites.c.id).where(favorites.c.user_id == user['id'], favorites.c.destination_key == identity)).scalar()

            if existing:

                connection.execute(update(favorites).where(favorites.c.id == existing).values(title=title, snapshot=payload, updated_at=now))

                favorite_id = existing

            else:

                favorite_id = str(uuid.uuid4())

                connection.execute(insert(favorites).values(id=favorite_id, user_id=user['id'], destination_key=identity,

                    title=title, snapshot=payload, created_at=now, updated_at=now))

    except IntegrityError:

        raise HTTPException(409, 'This trip was saved by another request. Open Saved trips to view it.')

    return {'status': 'saved', 'id': favorite_id}





# DELETE A PRIVATE SAVED TRIP
# DELETE /api/favorites/{favorite_id} requires write protection and current_user.
# Only delete if the record matches the provided favorite_id and its user_id matches the
# current user.
# Return 404 if no matching record owned by the current user was deleted.
# This deletes a saved trip not a landmark or image.
@router.delete('/api/favorites/{favorite_id}', dependencies=[Depends(protect_write)])

def remove_favorite(favorite_id: str, user=Depends(current_user)):

    with get_store().engine.begin() as connection:

        result = connection.execute(delete(favorites).where(favorites.c.id == favorite_id, favorites.c.user_id == user['id']))

        if not result.rowcount:

            raise HTTPException(404, 'Saved trip not found.')

    return {'status': 'deleted'}





# PREPARE AN UPLOADED IMAGE
# Validate the image as bytes. Remove any metadata and convert the image to a JPEG.
# Reject empty files or files over ten MiB with HTTP 413.
# Decode with Pillow and only accept JPEG, PNG or WebP images with at most 25000000
# pixels. Load the pixels and rotate if required by the EXIF orientation. Convert the
# pixels to RGB.
# Create a thumbnail sized to fit within 2400 by 2400 pixels without enlarging.
# Save a new JPEG image at quality 88 without passing through any metadata.
# Return HTTP 422 if there is a handled failure during decoding, format, or decompression.
def prepare_image(content):



    if not content or len(content) > 10 * 1024 * 1024:

        raise HTTPException(413, 'Choose a JPG, PNG or WebP image smaller than 10 MB.')

    try:

        with Image.open(io.BytesIO(content)) as source:

            if source.format not in ('JPEG', 'PNG', 'WEBP') or source.width * source.height > 25000000:

                raise ValueError()

            source.load()

            image = ImageOps.exif_transpose(source).convert('RGB')

            image.thumbnail((2400, 2400))

            output = io.BytesIO()

            image.save(output, format='JPEG', quality=88, optimize=True)

            return output.getvalue()

    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):

        raise HTTPException(422, 'That file is not a supported image. Choose a JPG, PNG or WebP image.')





# S3 CLIENT
# Import boto3 and create an S3 client using an optional custom endpoint.
# Use AWS_DEFAULT_REGION or auto, Signature Version 4, read and connection timeouts and
# the configured limited retry policy. Boto3 will handle credentials separately.
# If the required import fails return a 503 with a message regarding the dependency.
def s3_client():

    try:

        import boto3

        from botocore.config import Config

        return boto3.client('s3', endpoint_url=os.getenv('S3_ENDPOINT_URL') or None,

            region_name=os.getenv('AWS_DEFAULT_REGION', 'auto'),

            config=Config(signature_version='s3v4', connect_timeout=8, read_timeout=15, retries={'max_attempts': 1}))

    except ImportError:

        raise HTTPException(503, 'Install the updated backend requirements before using object storage.')





# STORE AN IMAGE
# Normalize the uploaded image prior to storage and assign a UUID to the image.
# Read the IMAGE_STORAGE setting. If this is database store the image as JPEG in the
# database. If this is s3 create a landmarks/{image_id}.jpg in S3.
# S3_BUCKET must be set before an image is uploaded as an image with content type
# image/jpeg.
# Log an object upload failure and return a 503 for any handled storage failures.
def store_image(content):

    data = prepare_image(content)

    image_id = str(uuid.uuid4())

    mode = os.getenv('IMAGE_STORAGE', 'database').lower()

    key = f'landmarks/{image_id}.jpg'

    if mode not in ('database', 's3'):

        raise HTTPException(503, 'IMAGE_STORAGE must be database or s3.')

    if mode == 's3':

        bucket = os.getenv('S3_BUCKET')

        if not bucket:

            raise HTTPException(503, 'Configure S3_BUCKET before using object storage.')

        try:

            s3_client().put_object(Bucket=bucket, Key=key, Body=data, ContentType='image/jpeg')

        except HTTPException:

            raise

        except Exception:

            logging.exception('Image object upload failed')

            raise HTTPException(503, 'Image storage is unavailable. Please try again later.')

    try:

        with get_store().engine.begin() as connection:

            # RECORD IMAGE STORAGE
            # Insert a trekmark_images record with a JPEG image stored in the database or
            # an object key in S3. Record mode and creation time for both.
            # After an S3 image is uploaded if the database record creation fails, attempt
            # to delete the uploaded object to prevent an uncommitted image from
            # remaining. Log a failure during cleanup and re-raise the creation error.
            # Return the image ID. The caller can use this to create a URL to the backend
            # image.
            connection.execute(insert(images).values(id=image_id, data=data if mode == 'database' else None,

                object_key=key if mode == 's3' else None, storage=mode, created_at=time.time()))

    except Exception:

        if mode == 's3':

            try:

                s3_client().delete_object(Bucket=os.environ['S3_BUCKET'], Key=key)

            except Exception:

                logging.exception('Could not remove uncommitted image object')

        raise

    return image_id





# DISCARD AN IMAGE
# Query for the image in a transaction.
# If the image is stored in S3 delete the object in S3 before deleting from the database.
# Delete the database record for either mode. S3 deletion and database deletion are
# separate operations. This function does not provide an atomic transaction across both
# operations.
def discard_image(image_id):

    with get_store().engine.begin() as connection:

        row = connection.execute(select(images).where(images.c.id == image_id)).mappings().first()

        if row and row['storage'] == 's3':

            s3_client().delete_object(Bucket=os.environ['S3_BUCKET'], Key=row['object_key'])

        connection.execute(delete(images).where(images.c.id == image_id))





# SERVE A LANDMARK IMAGE
# GET /media/{image_id}.jpg gets the image and returns 404 if not found.
# Get the JPEG data from the database or get the object from the configured S3 bucket and
# close the response after reading. Return a 503 on a handled S3 read failure.
# Set content-type to image/jpeg and set cache to one day public cache. Set nosniff.
# This endpoint is not dependent on current_user. Backend images can be publicly accessed
# by image ID regardless of the private or public nature of the associated S3 bucket.
# This endpoint serves images from landmarks. Private saved trips are scoped to users
# through separate authenticated endpoints.
@router.get('/media/{image_id}.jpg', name='landmark_media')

def media(image_id: str):

    with get_store().engine.connect() as connection:

        row = connection.execute(select(images).where(images.c.id == image_id)).mappings().first()

    if not row:

        raise HTTPException(404, 'Image not found.')

    data = row['data']

    if row['storage'] == 's3':

        try:

            body = s3_client().get_object(Bucket=os.environ['S3_BUCKET'], Key=row['object_key'])['Body']

            try:

                data = body.read()

            finally:

                body.close()

        except Exception:

            raise HTTPException(503, 'This image is temporarily unavailable.')

    return Response(content=data, media_type='image/jpeg', headers={

        'Cache-Control': 'public, max-age=86400', 'X-Content-Type-Options': 'nosniff'})
