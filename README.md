# Trekmark

## Image-driven travel planning

Click on a featured destination or upload an image to begin exploring! See images of that destination in the database. You can also discover nearby hotels, restaurants, and an airport.

**CSC 490 Senior Capstone  -  University of North Carolina at Greensboro**

[Watch or download the demo](assets/demo/TrekMark-Demo.mp4) · [Frontend](frontend/) · [Backend](backend/) · [Database resources](database/)

## Contents

- [Features](#features)
- [Repository guide](#repository-guide)
- [How the application connects](#how-the-application-connects)
- [Local setup](#local-setup)
- [Model and index files](#model-and-index-files)
- [API endpoints](#api-endpoints)
- [Team](#team)
- [Current limitations](#current-limitations)

## Features

| Feature | What users can do |
| --- | --- |
| Landmark recognition | Identify a supported landmark by uploading an image using DINOv2 and FAISS. |
| Featured destinations | View locations on a globe or through a gallery. |
| Destination profile | Read about the landmark and see images from the database to learn about other nearby landmarks. |
| Nearby places | Automatically find up to three hotels and three restaurants, each with their own image. |
| Airport information | Identify the closest airport and view directions using Google Maps. |
| Trip Canvas | Create/edit a three-day trip and navigate between its sections. |
| Traveler accounts | Log in and create an account to save a trip or delete or view previously saved trips. |
| Community submissions | Submit an image of a landmark with location information for review. |
| Administrator review | Delete, accept, reject, or edit community submissions. |

## Repository guide

| Location | Purpose |
| --- | --- |
| [`frontend/`](frontend/) | React interface, result components, destination adapter, and styling. |
| [`backend/`](backend/) | Recognition adapter, database interactions, accounts, travel services, and FastAPI application. |
| [`database/`](database/) | Information about the original database and community submission prototype. Currently used database and accounts code can be found at `backend/database.py` and `backend/accounts_api.py`. |
| [`landmark_ml/`](landmark_ml/) | Shared machine learning package and how to use recognition/indexing. Within the web application, see how to use the model at `backend/ml_service.py`. |
| [`tests/`](tests/) | Testing of the shared machine learning package |
| [`assets/demo/`](assets/demo/) | Video explaining the project |
| [`archive/backend-prototype/`](archive/backend-prototype/) | Previous version of the database and backend community submission code maintained for reference |
| [`pyproject.toml`](pyproject.toml) | Testing and dependencies of the shared machine learning package |

**`backend/main.py`** is used to start the application. The files in `archive/backend-prototype/` were used for an older version of the project and should not be used to run this project.

## How the application connects

1.  The React application sends an image to FastAPI at `POST /api/predict`.
2.  DINOv2 creates a 384-dimensional embedding, which is then searched against reference vectors using landmark ID.
3.  Results that are below the current threshold of 0.25 or are unknown are rejected before displaying a destination.
4.  After accepting the identified landmark ID, details about the landmark (location, images, etc.) are retrieved from Neon PostgreSQL.
5.  Geoapify is used to identify nearby destinations. For restaurants and hotels, Wikimedia Commons is used to provide an appropriate image (with attribution).
6.  In `frontend/src/destinationData.js`, the retrieved JSON data is transformed for display in destination preview and Trip Canvas.
7.  When a trip is edited, snapshots can be saved to Neon (only for authenticated users).

While using a separate FastAPI route to choose a featured destination, the same destination preview is used. Links will open in Google Maps to view destinations or get directions; the Google Maps JavaScript SDK is not embedded.

## Local setup

### Prerequisites

- Git to clone the project
- Node.js and npm to run the React application
- Python with the packages listed in `backend/requirements.txt`. Using Python 3.12 on a Mac with the instructions described in the documentation.
- Neon database with landmark and table information setup
- Geoapify API key used to identify nearby locations
- Local model and FAISS files to be used for identifying landmarks

This project does *not* download the model weights, index, or any private configurations. To view the files or use the database, reach out to the development team.

### Download the project

On Windows, open PowerShell. On macOS, open Terminal. Choose where you would like to save the project, and then:

```bash
git clone --branch cleanup/repository-organization https://github.com/mkramcharit/490-Senior-Captstone.git
cd 490-Senior-Captstone
```

This guide uses the organization branch, which currently has a new structure. Once it is merged into `main`, using `git clone` without `--branch cleanup/repository-organization` will use the well-organized main branch.

If you already have this branch on your computer, you should use your previously cloned project instead of cloning the project again.

Before starting the servers, reach out to the development team to receive your private settings and model/index bundle. In the below configuration, use your own authorized information. Simply cloning will not be able to provide database or recognition functionality.

For the database, either use the filled-out Neon database provided by the team with your authorization, or export the schema and landmark data to be used with your own Neon database. Because the database will be empty without this data, recognition and featured destinations will not function correctly. The contents of `database/` are for historical purposes, not fully used to create the current application.

### Configure the backend

In `backend/.env`, store your private information. During setup, you may also need:

```dotenv
DATABASE_URL=postgresql+psycopg2://USERNAME:PASSWORD@HOST/DATABASE?sslmode=require
GEOAPIFY_API_KEY=YOUR_GEOAPIFY_KEY
ADMIN_USERNAME=admin
ADMIN_PASSWORD=YOUR_ADMIN_PASSWORD
FRONTEND_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
IMAGE_STORAGE=database
```

For using your own local model to identify images, use `backend/.env.ml`:

```dotenv
DEMO_MODE=false
LANDMARK_MODEL_PATH=ml_assets/dinov2-small
LANDMARK_INDEX_PATH=ml_assets/dinov2-small/faiss-index
LANDMARK_DEVICE=cpu
```

These files are relative to the location of the backend. `.env.ml` is read *before* `.env`, but values from the shell and already-loaded variables will not be overridden. If both files have the same variable, the value from `.env.ml` will be used unless it has already been defined in the shell. Try to avoid conflicting configuration in both files and the shell. Whether the app is in demo mode can be seen in the backend at the `/` route.

Do not store any sensitive data in the React application or as part of a commit to Git. Replace any placeholders like `USERNAME`, `PASSWORD`, `HOST`, `DATABASE`, `YOUR_GEOAPIFY_KEY`, and `YOUR_ADMIN_PASSWORD` with your own information. Keep the other configurations as listed to use this local setup. Using `IMAGE_STORAGE=database` will store the images (as bytes) you submit to Neon. Alternatively, you could use a private S3-compatible option but would need to configure it yourself.

### Start the backend on Windows

For a new project, start in the root of the project using Python 3.12 for your environment:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

If you already have your virtual environment set up and have installed the packages, only run the `cd backend` and the uvicorn commands in a new terminal at the root of the project.

### Start the backend on macOS

From the root of the project using Python 3.12:

```bash
cd backend
python3.12 -m venv .venv-mac
./.venv-mac/bin/python -m pip install -r requirements.txt
./.venv-mac/bin/python -m uvicorn main:app --reload
```

Each computer will create its own virtual environment. On different computers, a new virtual environment will have to be created.

### Start the frontend

From another terminal at the root of the project:

```bash
cd frontend
npm ci
npm run dev
```

| Service | Local address |
| --- | --- |
| Website | [http://localhost:5173/](http://localhost:5173/) |
| Backend | [http://localhost:8000/](http://localhost:8000/) |
| Interactive API documentation | [http://localhost:8000/docs](http://localhost:8000/docs) |

If port 5173 is already in use, use the address indicated by Vite. Additionally, you should also add this to `FRONTEND_ORIGINS`. Both the frontend and backend should use the same address (e.g., both using `localhost`) so that traveler cookies are appropriately used. Both servers run on different ports.

By default, the frontend will use the same address as the website, but on port 8000. To override this, you can update `VITE_API_BASE_URL` in `frontend/.env.local` and then re-run Vite.

### Verify the setup and run it again

1. Keep both terminals open. Look for `Application startup complete` in the backend terminal and for Vite to indicate its local address.
2. Go to [http://localhost:8000/](http://localhost:8000/) to verify the backend response. Based on the above configuration, demo mode should be turned off.
3. Go to [http://localhost:5173/](http://localhost:5173/) and select a featured destination to verify that the database can be accessed.
4. Upload an image of a supported landmark to verify both the model and index. Actual recognition will require the files listed below. Depending on the size of the model, the first request may take some time to load.
5. Check that nearby destinations can be identified, create an account as a traveler and save a trip to confirm that account data persists.

To shut down a server, press **Ctrl+C** in its terminal.

For future use, no configuration will be needed unless there are changes to the dependencies. From the root of the project, start the backend using the appropriate command:

**Windows - terminal 1**

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

**macOS - terminal 1**

```bash
cd backend
./.venv-mac/bin/python -m uvicorn main:app --reload
```

**Either system - terminal 2, starting from the project root**

```bash
cd frontend
npm run dev
```

If you get an error saying that `py`, `python3.12`, `git`, or `npm` are not recognized, install the appropriate prerequisite and then reopen your terminal. If you are unable to recognize landmarks, verify the proper files and matching bundle below and check the backend terminal. If you are unable to access the database, verify that your authorized Neon database connection string and the necessary data are present. It is possible to have a landmark accepted even if neither a photo nor a location is found through an external search.

## Model and index files

If you do not already have these directories created, create them and place the matching model and index bundle inside before attempting to recognize landmarks:

| Directory | Required files |
| --- | --- |
| `backend/ml_assets/dinov2-small/` | `config.json`, `preprocessor_config.json`, `model.safetensors` |
| `backend/ml_assets/dinov2-small/faiss-index/` | `images.faiss`, `references.json` |

The model, index, and reference data must be compatible. The 384-dimensional data indicates a representation of an image rather than the number of images associated with a landmark.

Private configuration and model files are not committed to Git. Updating the database in Neon will not automatically update the index.

## API endpoints

| Method and route | Purpose |
| --- | --- |
| `POST /api/predict` | To identify the landmark in an uploaded image |
| `GET /api/featured/{preset_id}` | To identify the destination that was chosen as featured |
| `GET /api/landmark/{landmark_id}` | To identify details about a specific landmark |
| `GET /api/hotels` | To identify nearby hotels |
| `GET /api/restaurants` | To identify nearby restaurants |
| `GET /api/airports` | To identify details about the nearest airport |
| `POST /api/auth/register` | To register as a traveler |
| `POST /api/auth/login` | To log in as a traveler |
| `GET /api/favorites` | Retrieve traveler's saved trips (for the currently logged in user) |
| `POST /api/favorites` | To save a trip (snapshot) to a traveler's favorites |
| `POST /submission` | To submit a photo of a landmark (with location information) for review |
| `POST /admin/login` | To log in as an administrator |

In addition to the above endpoints, the interactive API documentation for the currently running backend includes information about review, deletion, and accounts (among others). Although both users and administrators have similar login processes, they use different authentication within the backend.

## Team

| Member | Primary project area |
| --- | --- |
| Michael Ramcharitar | Developing and integrating the React interface |
| Michael Chapman | Using machine learning/recognizing landmarks via FAISS and embeddings |
| Brycen | Using external services and creating backend APIs and caching |
| Chris | Creating database content, location information, and images |

## Current limitations

- The matching score is not actually verified to be accurate; the threshold of 0.25 should be tested using sample images
- Landmark recognition requires that the correct references have been added to the index
- Featured destinations require that the Neon database be set up with similar information
- Because of image availability, less than three hotels or restaurants may be returned per category
- The distances indicated are based on proximity rather than guaranteed travel time (by walking or driving)
- While trips can be initially created as editable, there are currently no features implemented to book, determine current availability/pricing, or optimize the trip
- Saving trips is currently supported but there is no feature implemented to track a user's history of submitted images
- Currently, communication between the browser and backend (locally) is done using HTTP rather than HTTPS; in a public setting, HTTPS and other production features would be needed
- Images of landmarks are pulled from the database. Images of hotels and restaurants are pulled from Wikimedia Commons. Attribution should still be visible within the application.
