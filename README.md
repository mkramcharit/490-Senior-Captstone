# Trekmark

## Image-driven travel planning

Click on a featured destination or upload an image to begin exploring! You can see images of that destination in the database and also learn about nearby restaurants, hotels, and an airport.

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
| Landmark recognition | Using FAISS and DINOv2, identify a supported landmark by uploading an image. |
| Featured destinations | View destinations through a gallery or on a globe. |
| Destination profile | Learn more about the landmark (images from the database, etc.) and see information about other nearby landmarks. |
| Nearby places | Up to three restaurants and three hotels will be automatically found, each with their own image. |
| Airport information | Find the closest airport and see directions using Google Maps. |
| Trip Canvas | Edit or create a three-day trip and move between its sections. |
| Traveler accounts | Create or log in to an account to save or view/delete previously saved trips. |
| Community submissions | Submit an image of a landmark (with location information) to be reviewed. |
| Administrator review | Accept, reject, edit or delete community submissions. |

## Repository guide

| Location | Purpose |
| --- | --- |
| [`frontend/`](frontend/) | Styling, destination adapter, result components, and React interface. |
| [`backend/`](backend/) | FastAPI application, accounts, travel services, and database interactions. |
| [`database/`](database/) | Information about the original database and community submission prototype. For now, `backend/database.py` and `backend/accounts_api.py` are currently used for the database and accounts. |
| [`ml_model/`](ml_model/) | Shared machine learning tools for indexing/recognition and a package. Source code is located at `ml_model/landmark_ml/`. The web application uses its separate recognition adapter at `backend/ml_service.py`. |
| [`ml_model/tests/`](ml_model/tests/) | Testing the shared machine learning package |
| [`scripts/`](scripts/) | Tools for evaluating, indexing, calibration, and collecting images, originally from `main` |
| [`docs/`](docs/) | Reports regarding confidence/validation and reference-data, originally from `main` |
| [`assets/demo/`](assets/demo/) | A video explaining the project |
| [`archive/backend-prototype/`](archive/backend-prototype/) | Maintained for reference: previous version of the backend and community submission database code |
| [`archive/ml-prototype/`](archive/ml-prototype/) | Maintained for reference: previous machine learning package and its tests |
| [`pyproject.toml`](pyproject.toml) | Testing the shared machine learning package and its dependencies |

To run the application, use `backend/main.py`. `archive/backend-prototype/` was used for an earlier version of the project and should not be used for this one.

## How the application connects

1.  Using `POST /api/predict`, the React application will send an image to FastAPI.
2.  Using DINOv2, an embedding will be created of dimension 384, which will be searched using landmark ID against reference vectors.
3.  Any unknown or below the 0.25 threshold results will be rejected before displaying a destination.
4.  Once the identified landmark ID is accepted, Neon PostgreSQL will be used to retrieve information about that landmark (images, location, etc.).
5.  Geoapify will be used to determine nearby destinations; for hotels and restaurants, Wikimedia Commons will be used to provide a suitable image (with attribution)
6.  In `frontend/src/destinationData.js`, JSON data retrieved will be altered to be displayed in both the destination preview and Trip Canvas
7.  When editing a trip, snapshots can be saved to Neon (only if the user is logged in).

When selecting a featured destination through a separate FastAPI route, the same destination preview is used. Links will open in Google Maps to either view destinations or get directions; there will *not* be an embedded Google Maps JavaScript SDK.

## Local setup

### Prerequisites

- Git to clone the project
- Node.js and npm to run the React application
- Python with the packages listed in `backend/requirements.txt`. Using Python 3.12 on a Mac using the instructions in the documentation provided
- Neon database with table and landmark information set up
- Geoapify API key to be used to identify nearby destinations
- Local model and FAISS files to be used to identify landmarks

*Note:* This project does not download any private information, including the model weights, index, or anything else. To access the database or view these files, please contact the development team.

### Download the project

On Windows, open PowerShell. On macOS, open Terminal. Select where to save the project and then:

```bash
git clone --branch cleanup/repository-organization https://github.com/mkramcharit/490-Senior-Captstone.git
cd 490-Senior-Captstone
```

This guide uses the organization branch (which is currently in a new format) but once the branch has been merged into `main`, you will be able to simply `git clone` without `--branch cleanup/repository-organization` to use the well-organized main branch.

If you already have this branch on your computer, you should instead use the previously cloned project rather than cloning the project again.

Before starting to run the servers, please contact the development team to receive your model/index bundle and private settings. In the configuration below, replace the information with your own authorized information. Simply cloning will not be able to allow you to access the database or use recognition.

For the database, you can either use the filled-out Neon database provided by the development team with your authorization or export the table and landmark data to be used with your own Neon database. Without this information, the database will be empty, so both featured destinations and recognition will likely be inaccurate. Please note that the information in `database/` is for historical purposes and was not fully used to build the current application.

### Configure the backend

Place your private information in `backend/.env`. You may also need to add the following during set up:

```dotenv
DATABASE_URL=postgresql+psycopg2://USERNAME:PASSWORD@HOST/DATABASE?sslmode=require
GEOAPIFY_API_KEY=YOUR_GEOAPIFY_KEY
ADMIN_USERNAME=admin
ADMIN_PASSWORD=YOUR_ADMIN_PASSWORD
FRONTEND_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
IMAGE_STORAGE=database
```

To use a local model to identify images, use `backend/.env.ml`:

```dotenv
DEMO_MODE=false
LANDMARK_MODEL_PATH=ml_assets/dinov2-small
LANDMARK_INDEX_PATH=ml_assets/dinov2-small/faiss-index
LANDMARK_DEVICE=cpu
```

These are relative to the location of the backend. `.env.ml` will be read before `.env`, but values already set in the shell will not be overridden by either file. If both files have the same information, `.env.ml` will be used unless it has already been defined in the shell. Try to avoid having conflicting information in both files and in your shell. In the backend, you can see if the application is in demo mode by visiting the `/` route.

Do *not* add any private information to the React application or commit that information to Git. Replace any of the following information with your own: `USERNAME`, `PASSWORD`, `HOST`, `DATABASE`, `YOUR_GEOAPIFY_KEY`, and `YOUR_ADMIN_PASSWORD`. Leave all other information as listed in this local set up guide to use this local setup. Using `IMAGE_STORAGE=database` will save the images (as bytes) you upload to Neon. Alternatively, you can use a private S3-compatible option but you would have to set this up yourself.

### Start the backend on Windows

If this is a new project, start in the root of the project using Python 3.12 as your environment:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

If you already have your virtual environment set up and have already installed the packages, you only need to run the `cd backend` and the uvicorn commands in a new terminal at the root of the project.

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

From a separate terminal at the root of the project:

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

If you are already using port 5173, you should use the address indicated by Vite. Additionally, you should also add this to `FRONTEND_ORIGINS`. Both the frontend and backend should use the same address (i.e., both using `localhost`) to ensure that traveler cookies are properly used. Both servers are on different ports.

By default, the frontend will use the same address as the website but on port 8000. To override this, you can update `VITE_API_BASE_URL` in `frontend/.env.local` and then re-run Vite.

### Verify the setup and run it again

1. Keep both terminals open. In the backend terminal, look for `Application startup complete` and in the Vite terminal for it to indicate a local address.
2. Confirm that the backend responds correctly by visiting [http://localhost:8000/](http://localhost:8000/). Using the configuration above, you would expect it to *not* be in demo mode
3. Confirm that you can access the database by visiting [http://localhost:5173/](http://localhost:5173/) and selecting a featured destination.
4. Finally, confirm that both the model and index work by uploading an image of a supported landmark. You will not be able to perform recognition until using the following files below. Depending on the size of the model, this may take some time to load on the first request.
5. Confirm you can identify nearby destinations and create an account as a traveler to save a trip and confirm that account data persists.

To shut down a server, press **Ctrl+C** in its terminal.

For the future, no configuration will be necessary unless you have changed the dependencies. From the root of the project, start the backend using the appropriate command:

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

If you get an error stating that `py`, `python3.12`, `git`, or `npm` are not recognized, install the appropriate prerequisite and then re-open your terminal. If you are unable to recognize landmarks, please verify the proper files and matching bundle below and check the backend terminal. If you are unable to access the database, please check that you have the proper authorized Neon database connection string and that the necessary data is present. You can still have a landmark accepted even if neither location nor a photo is found through an external search.

## Model and index files

If you do not already have these directories created, create them and place the matching model and index bundle inside before attempting to recognize landmarks:

| Directory | Required files |
| --- | --- |
| `backend/ml_assets/dinov2-small/` | `config.json`, `preprocessor_config.json`, `model.safetensors` |
| `backend/ml_assets/dinov2-small/faiss-index/` | `references.json`, `images.faiss` |

The 384-dimensional data indicates that this is representing an image, not the number of images associated with a landmark - these must be compatible.

Private information and model files are not committed to Git. Updating the database in Neon will not automatically update the index.

## API endpoints

| Method and route | Purpose |
| --- | --- |
| `POST /api/predict` | To identify the landmark in the uploaded image |
| `GET /api/featured/{preset_id}` | To identify the destination that was selected as featured |
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

In addition to the above endpoints, interactive API documentation for the currently running backend (among other information) details information about accounts, review and deletion (among others). Although both users and administrators have similar login processes, they both authenticate differently within the backend.

## Team

| Member | Primary project area |
| --- | --- |
| Michael Ramcharitar | Building and integrating the React interface |
| Michael Chapman | Using machine learning to recognize landmarks using embeddings and FAISS |
| Brycen | Utilizing external resources to create backend APIs and caching |
| Chris | Creating images, location information, and database content |

## Current limitations

- The threshold of 0.25 should be verified to be accurate (using sample images)
- Recognition requires that the correct references have been added to the index
- Featured destinations require that similar information be set up in the Neon database
- Due to the availability of images, less than three restaurants or hotels may be returned per category
- The distances listed are based on proximity, not guaranteed travel time (by walking or driving)
- While trips can be created as editable, no features have currently been implemented to either optimize the trip, determine current pricing/availability, or to book
- Saving trips is currently supported, but no feature has been implemented to track a user’s history of submitted images
- Currently, the way that the browser and backend (locally) communicate uses HTTP rather than HTTPS; in a public setting, HTTPS and other production features would be necessary
- Landmark images are pulled from the database. Restaurant and hotel images are pulled from Wikimedia Commons. Attribution should still be visible within the application.
