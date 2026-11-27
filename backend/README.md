# Trekmark Backend

API connecting React frontend to nearby travel, accounts, landmark recognition, and a PostgreSQL database (Neon).

[Project overview and setup](../README.md) · [Frontend](../frontend/) · [Database resources](../database/)

## Setup

Before running the server, please follow the instructions in the [root README for local setup](../README.md#local-setup). This involves cloning the repo, installing dependencies, setting up private settings, and getting appropriate model/index files.

Because the code is cloned fresh, there will be no private settings, model or index files. Additionally, connected features require a database with the expected structure and data (landmarks).

Private settings should be placed in `backend/.env` and `backend/.env.ml`. Please do not commit any sensitive information (like private settings) to Git or into the frontend.

## Start the server

These instructions assume you have already set up the virtual environment and installed dependencies. Start in the root of the project.

### Windows

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

### macOS

```bash
cd backend
./.venv-mac/bin/python -m uvicorn main:app --reload
```

Leave this terminal open while using the application. To stop the server, press **Ctrl+C**.

| Service | Local address |
| --- | --- |
| Backend status | [http://localhost:8000/](http://localhost:8000/) |
| Interactive API documentation | [http://localhost:8000/docs](http://localhost:8000/docs) |
| Frontend (started separately) | [http://localhost:5173/](http://localhost:5173/) |

The currently running application is `backend/main.py`. The older version located at `archive/backend-prototype/` has been preserved for historical purposes.

## Main files

All files listed below are relative to `backend/`.

| File | Purpose |
| --- | --- |
| [`main.py`](main.py) | FastAPI app, request flow for landmark recognition, responding with destinations, handling submission and admin routes. |
| [`ml_service.py`](ml_service.py) | Loads local FAISS and model files. Used to adjust landmark recognition for use in the frontend application. |
| [`database.py`](database.py) | Handles interactions with the database for landmarks (photos, coordinates, records), community submissions, and nearby landmarks. |
| [`accounts_api.py`](accounts_api.py) | Handles traveler accounts, sessions, saved itineraries, and image storage. |
| [`featured_service.py`](featured_service.py) | Matches configured featured landmarks against the database of landmarks. |
| [`hotels_service.py`](hotels_service.py) | Finds nearby hotels based on landmark coordinates. |
| [`restaurants_service.py`](restaurants_service.py) | Finds nearby restaurants based on landmark coordinates. |
| [`airports_service.py`](airports_service.py) | Finds nearby airport information based on landmark coordinates. |
| [`hotel_photos.py`](hotel_photos.py) | Finds photos from Wikimedia Commons for matches as a restaurant or hotel result, including attribution. |
| [`category_format.py`](category_format.py) | Formats names of submitted categories for consistency. |
| [`requirements.txt`](requirements.txt) | Lists dependencies used by the currently running application. |
| [`.env.example`](.env.example) | Example of how to setup the application environment; use a private local file with actual information. |

## Recognition and destination flow

1. The frontend sends an image to `POST /api/predict`.
2. Using FAISS and DINOv2, landmark recognition returns a landmark and confidence score.
3. Before returning a destination, the backend enforces a recognition acceptance policy.
4. Using the landmark ID accepted by the policy, the application can connect to its Neon record (photo, coordinates), etc.
5. Using the coordinates, nearby airport, hotel, and restaurant information can be found.
6. The result is returned as JSON for the frontend to render the destination and travel information.

Featured landmarks have their own route but still follow the destination flow. If no match is found or landmark recognition fails for some reason, user feedback will need to differ. The confidence score does not represent a calibrated measure of accuracy.

## External services and persistence

| Service | Role |
| --- | --- |
| Neon PostgreSQL | Stores traveler accounts, sessions, snapshots of saved itineraries, landmark data, and image data stored via the database. |
| Geoapify | Provides information about nearby hotels, restaurants, and airports. |
| Wikimedia Commons | Provides suitable image data for hotels and restaurants with attribution. |
| Google Maps links | Open a location or give directions using a URL and coordinates. |

Landmark images are stored in database records. Using Wikimedia Commons to find images only applies to hotel and restaurant results. Due to image availability, there may be fewer than three results per category.

Image storage can be either using data from the database or a separately-configured service like S3. Accepting a community-submitted result does not automatically rebuild the FAISS index.

## Configuration and troubleshooting

- `.env.ml` is read before `.env` in `main.py`. Neither will override values already set in the shell or previously read from the file. Try to avoid having conflicting configurations.
- Setting `DEMO_MODE=false` will use the actual landmark recognition path. View the backend at its root endpoint (`/`) to verify which mode is currently being used.
- Make sure the model, preprocessing configuration file, FAISS index, and mapping file are all compatible. More details about required files and paths can be found in the [root README](../README.md#model-and-index-files).
- Use the same domain name for the frontend and backend. Add the frontend domain to `FRONTEND_ORIGINS`.
- If landmark recognition, database, or external service requests fail, check the backend terminal.
- While both travelers and administrators use the same interface in the frontend, they use different authentication methods in the backend.

The commands shown above are for local development only. For a live deployment, you will need to use an appropriate production configuration (using HTTPS, for example).

To see all currently recognized routes and request structures, check out the [interactive API documentation](http://localhost:8000/docs) running on the server.
