# Three goals for this code: 
# 1. The user needs to be able to submit landmarks to be added to the database
# 2. The admins need to be able to review landmarks and either reject or approve them
# 3. Once we have enough (30) approved images for a landmark in our holding table, 
#    we want to move all the related rows from the holding table to the actual training_data table

from fastapi import FastAPI, HTTPException, WebSocketException
from pydantic import BaseModel
from sqlalchemy import create_engine, text
import pandas as pd

app = FastAPI(title="TO-DO: APPNAME")

engine = create_engine(
    "postgresql+psycopg2://landmarks_owner:npg_jcmM5DsKEr1b@ep-dry-breeze-a5wcb604-pooler.us-east-2.aws.neon.tech/landmarks?sslmode=require&channel_binding=require"
)

APPROVAL_THRESHOLD = 30 

# TO-DO: ALL OF THESE FUNCTIONS PROBABLY NEED SOME INPUT SANITIZATION.

# TO-DO: CURRENTLY, WE ARE JUST USING URL:STR HERE, BUT WILL THE USER BE SUBMITTING URLS, OR IMAGES?
# OUR TABLES DON'T STORE IMAGES. MUST CONSIDER EITHER THIRD PARTY STORAGE WITH A URL LINKING TO IT 
# THAT WE SHUFFLE EVERYTHING INTO, THIS COMES WITH A LOT OF HEADACHES (SECURITY, NEW DATABASE?).
# MAYBE CONSIDER JUST STORING IT IN THE DATABASE. IF SO, GOTTA CHANGE URL:STR
class Submission(BaseModel):
    url: str 
    landmark_id: int
    name: str
    lat: float
    lon: float
    country: str
    city: str
 
@app.post("/submission")
def new_submission(submission: Submission):
    """Post method for user submission"""
    with engine.connect() as connection: 
        connection.execute(text("""
        INSERT INTO user_submissions (url, landmark_id, name, lat, lon, country, city)
        VALUES (:url, :landmark_id, :name, :lat, :lon, :country, :city)"""), 
        submission.model_dump()) #Converts pydandtic stuff into a python dictionary

    return {} #TO-DO: FIGURE OUT WHAT RETURN SHOULD BE

@app.post("/submissions/{submission_id}/approve")
def approve_submission(submission_id: int):
    """Post for admin approving a submission"""
    with engine.begin() as connection: #TO-DO: SHOULD THIS BE CONNECT?
        result = connection.execute(text("""
        UPDATE user_submissions
        SET status = 'approved',
        WHERE submission_id = :submission_id"""), 
        {"submission_id": submission_id}) # IS THIS LINE RIGHT?

    if result.rowcount == 0:
        raise HTTPException(404, detail = "Error: No matching item") # TO-DO: FIGURE OUT WHAT EXCEPTION TO RAISE HERE

    return {} # TO-DO: FIGURE OUT WHAT RETURN SHOULD BE
   
# TO-DO: consider changing this so that we keep the rejected submissions? so we don't get duplicates 
@app.post("/admin/{submission_id}/reject")
def reject_submission(submission_id: int):
    """Post for when admin rejects a submission"""
    with engine.begin() as connection:
        result = connection.execute(text("""
        UPDATE user_submissions
        SET status = 'rejected', 
        WHERE submission_id = :submission_id"""), 
        {"submission_id": submission_id}) # IS THIS LINE RIGHT?

    if result.rowcount == 0:
        raise HTTPException(404, detail = "Error: No matching item") # TO-DO: FIGURE OUT WHAT EXCEPTION TO RAISE HERE

    return {} # TO-DO: FIGURE OUT WHAT RETURN SHOULD BE


@app.post("/migrate")
def migrate_approved():
    """Post method for moving entries from user_submission table to training_data table"""
    check_query = text("""
        SELECT landmark_id
        FROM user_submissions
        WHERE status t 'approved'
        GROUP BY landmark_id
        HAVING COUNT(*) >= :threshold""")

    insert_query = text("""
        INSERT INTO training_data (id, url, landmark_id, name, lat, lon, country, city)
        SELECT id, url, landmark_id, name, lat, lon, country, city
        FROM user_submissions
        WHERE status = 'approved'
        AND landmark_id IN (
        TO-DO: THIS SQL QUERY)""")

    delete_query = text("""
        TO-DO""")
    
    with engine.begin() as connection:
       # TO-DO: ENGINE SECTION FOR THIS METHOD, IT WILL PROBABLY BE ANNOYING

    return {} # TO-DO: FIGURE OUT WHAT RETURN SHOULD BE