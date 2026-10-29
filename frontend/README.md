# Trekmark — Frontend/Backend Integration

Trekmark is a travel planning app based on images.

The frontend code is React-based and resides in the frontend directory. The backend integration is a completely rewritten FastAPI backend which includes database access, external API access, authentication, saved itineraries, landmark submissions, and integration with ML.

This document explains both the front end and back end as well as how they work with each other. Frontend file paths below start in `frontend`; backend file paths start in `backend-integration`.


> **Project overview:** React frontend · FastAPI backend · DINOv2 + FAISS recognition · Neon database · Geoapify + Wikimedia Commons

## Contents

- [Current features](#current-features)
- [Frontend files](#frontend-files)
- [Backend overhaul](#backend-overhaul)
  - [Backend files](#backend-files)
  - [Backend endpoints](#backend-endpoints)
  - [API integration and caching](#api-integration-and-caching)
  - [Accounts, saved itineraries and image storage](#accounts-saved-itineraries-and-image-storage)
  - [Backend configuration and ML components](#backend-configuration-and-ml-components)
- [Frontend URLs used for the backend](#frontend-urls-used-for-the-backend)
- [Frontend integration with backend](#frontend-integration-with-backend)
- [Services used by Trekmark](#services-used-by-trekmark)
- [Run locally](#run-locally)
- [Frontend configuration](#frontend-configuration)
- [Known problems and future work](#known-problems-and-future-work)

---

## Current features

### Landmark recognition

- Image-based landmark identification via integration of a machine learning model (DINOv2) and FAISS index of landmark images into a FastAPI backend
- Recognition result as a similarity score or unknown if the recognition result does not pass the recognition policy
- Featured landmarks based on landmarks from the back end
- Landmark images based on data returned from the Neon database by the back end

### Travel planning

- Automatically obtained nearby restaurants and hotels with up to three photo results for both
- Google Maps links to open a location or get directions
- Nearby airport with Google Maps directions
- Three-day itinerary that can be edited and has two options to save the itinerary

### Accounts and landmark management

- Traveler account creation, login and saved itineraries
- Shared login interface and access for both travelers and administrators
- Community submitted landmarks using image files instead of URLs
- Forms and administrator interface for managing landmarks

### User interface

- Animations, transitions, travel backgrounds, and responsive design

---

## Frontend files

All files with a `.jsx` extension contain JavaScript with React syntax.

| File | Purpose |
| --- | --- |
| `src/main.jsx` | Upload of images, destination preview, Trip Canvas, navigation and component integration |
| `src/destinationData.js` | Adapter for converting back end JSON response data into destination data for use by frontend code and mapping featured destinations to preset IDs |
| `src/HotelResults.jsx` | Display of hotel results. Used by `main.jsx` |
| `src/RestaurantResults.jsx` | Display of restaurant results. Used by `main.jsx` |
| `src/AirportResults.jsx` | Display of nearby airport. Used by `main.jsx` |
| `src/AccountPanel.jsx` | Traveler account management and itinerary editing. Used by `main.jsx` |
| `src/AdminPage.jsx` | Administrator landmark management |
| `src/styles.css` | Primary styling, animations, travel background, and responsive design |
| `src/hotels.css` | Styling for hotel and restaurant results |
| `index.html` | Entry point for the web page with a location for the React component root |
| `package.json` | Build and dependencies for frontend code |

> **Adapter requirement:** The `destinationData.js` adapter file must exist in the `frontend/src` directory and must export functions used by `main.jsx`. It cannot be empty in the working version of the app. If your version has a different file name or is stored in a different directory, you can adjust the import in `main.jsx` accordingly.

This adapter is app code and is separate from any environment or machine specific settings found in a `.env.local` file.

---

## Backend overhaul

The back end has been expanded from the demo version to the integration used in the app. It provides a common FastAPI backend to connect to the recognition model, travel APIs, and Neon database from the front end code.

The backend has implemented the following:

- Instead of using a preset ID to match an uploaded image to a landmark, if image recognition is enabled it maps an image to the DINOv2 model and the FAISS index
- Given an accepted landmark ID it can look up the landmark name, photo, coordinates, and nearby landmarks using data in Neon
- Uses landmark coordinates to search for nearby hotels and restaurants and uses a different search to get nearby airports
- Integrates Wikimedia Commons photos into responses used by the front end code and uses Geoapify place data
- Implements caching of place searches in order to reduce number of external searches
- Implements traveler accounts and private saved itineraries
- Allows upload of image files for landmarks and allows for storage and delivery of image files from the back end
- Implements administrator login, submission review, and formatting of category names
- Implements request validation, readable error responses and configurable allowed origins for the browser

### Backend files

| File | Purpose and connection to the app |
| --- | --- |
| `main.py` | Entry point for a FastAPI backend. Receives requests from the front end, connects to the ML and database, connects to the place APIs, implements account functionality and provides submission and administrator access |
| `ml_service.py` | Loads the recognition model and index, creates a representation of an uploaded image and performs recognition using the FAISS index and recognition policy. The results from this component are used by main.py to look up data from Neon based on a matched landmark ID |
| `database.py` | Connects to Neon and provides functionality for looking up landmarks, photos, nearby landmarks, and submissions. The account component also uses a database from this module |
| `featured_service.py` | Maps featured destination selections to data from Neon based on landmark data and coordinates |
| `hotels_service.py` | Uses Geoapify to search for nearby hotels, requests images for these hotels using `hotel_photos.py` and caches these results. This component is used in place search results and by the /api/hotels endpoint |
| `restaurants_service.py` | Uses Geoapify to search for nearby restaurants, requests images for these restaurants using `hotel_photos.py` and caches these results. This component is used in place search results and by the /api/restaurants endpoint |
| `airports_service.py` | Uses Geoapify to search for a nearby airport and provide the airport info |
| `hotel_photos.py` | A shared function used for obtaining images for both hotels and restaurants from Wikimedia Commons including attribution for images |
| `accounts_api.py` | Account creation, account login and session creation for travelers, private saved itineraries, and image storage and delivery |
| `category_format.py` | Formats category names to be used by the administrator workflow as `Category:Category_Name` |
| `requirements.txt` | Dependencies required by the backend |

These filenames are the runtime filenames used for imports. If a downloaded version of the code has a different name, such as `featured_destinations.py`, it must be installed with the expected name or all imports must be adjusted accordingly.

### Backend endpoints

| Method and route | Purpose |
| --- | --- |
| `GET /` | Provides information about whether the backend is running and whether demo mode is enabled |
| `GET /api/health` | Provides health information about the backend |
| `POST /api/predict` | Receives an image upload and returns recognition results and, if an accepted result is obtained, data about the matching landmark including landmark data from Neon and nearby hotel and restaurant data from Geoapify |
| `GET /api/landmark/{landmark_id}` | Returns information about a landmark with the given landmark id |
| `GET /api/featured/{preset_id}` | Returns information about a featured destination selection |
| `GET /api/hotels` | Returns information about nearby hotels given a location and search criteria |
| `GET /api/restaurants` | Returns information about nearby restaurants given a location and search criteria |
| `GET /api/airports` | Returns information about a nearby airport given a location |
| `POST /api/auth/register` | Registers a new traveler account |
| `POST /api/auth/login` | Authenticates a traveler and creates a session cookie |
| `GET /api/auth/me` | Returns authenticated traveler |
| `POST /api/auth/logout` | Clears authenticated traveler session |
| `GET /api/favorites` | Returns saved itineraries associated with the current authenticated traveler |
| `POST /api/favorites` | Saves an itinerary for the current authenticated traveler |
| `DELETE /api/favorites/{favorite_id}` | Deletes a saved itinerary for the current authenticated traveler |
| `POST /submission` | Receives information about a community submitted landmark including an image file |
| `GET /media/{image_id}.jpg` | Returns a stored landmark image |
| `POST /admin/login` | Authenticates an administrator |

Additional admin endpoints exist for managing submissions, searches, reviews, edits, and deletions. Exact routes and fields for requests can be viewed at the interactive API documentation for the running backend at [http://localhost:8000/docs](http://localhost:8000/docs)

### API integration and caching

When searching for nearby places the back end uses the latitude and longitude of a landmark for requests to Geoapify. Users do not need to manually copy any coordinates to a request to an external API and the browser does not need a Geoapify key.

There are separate implementations for finding nearby hotels and restaurants. Each component searches for places and attempts to obtain an appropriate photo using `hotel_photos.py`. A maximum of three places with photos are returned. If the resulting image for a place fails to load it can be removed from the front end display.

Hotel and restaurant searches are normally cached for ten minutes. Searches that are limited by place search budget are cached for a shorter time. Caches are in-memory and are cleared when the backend server is restarted. These caches are separate from any persistent data stored in Neon.

Wikimedia Commons provides best effort photos of both hotels and restaurants. These photos are not replacements for landmark photos provided by Neon. Google Maps links are used for opening locations or directions but does not provide place search data.

### Accounts, saved itineraries and image storage

Traveler accounts, password hashes, saved itineraries and traveler sessions are stored in Neon. Passwords are salted and hashed and plaintext passwords are not stored. The browser holds the traveler session token in an HTTP-only cookie; session records are stored in Neon. Saved itineraries can only be accessed by their authenticated owner.

The account component uses the existing Trekmark tables in Neon: `trekmark_users`, `trekmark_sessions`, `trekmark_favorites`, and `trekmark_images`. A saved itinerary contains a state of a trip including the currently edited itinerary and can be retrieved later.

Community submitted landmarks can be submitted using image files. By default image bytes are stored in Neon. An alternative implementation is also available which stores images in a private S3-compatible bucket if the image storage setting is set to `s3` and settings for the S3 bucket are available. Image files can be delivered via backend media URLs. Accepting an image does not imply that S3 is enabled.

Administrator credentials are configured on the backend. Administrator sessions are stored using temporary in-memory tokens and are cleared on server restart. A shared login interface provides access for both travelers and administrators; their backend authentication mechanisms are separate.

### Backend configuration and ML components

| Setting | Purpose |
| --- | --- |
| `DATABASE_URL` | URL for the Neon PostgreSQL database |
| `GEOAPIFY_API_KEY` | Key used for making requests to Geoapify. This key can be provided in environment variables or in the backend's environment files |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | Administrator credentials |
| `FRONTEND_ORIGINS` | Comma separated list of allowed origins for the browser. This should include both protocol and port |
| `DEMO_MODE` | If set to false then real image recognition is enabled. If set to true then a fixture result will be returned instead |
| `LANDMARK_MODEL_PATH` | Local path to the folder containing the DINOv2 model |
| `LANDMARK_INDEX_PATH` | Local path to the folder containing the FAISS index |
| `LANDMARK_DEVICE` | Device used for image recognition: e.g. cpu |
| `IMAGE_STORAGE` | Mode of image storage: `database` by default, or `s3` when configured |

#### Required ML files

| Location | Files | Role |
| --- | --- | --- |
| Model folder | `config.json`, `preprocessor_config.json`, and model weights such as `model.safetensors` | Model configuration, image preprocessing, and learned weights. |
| Index folder | `images.faiss`, `references.json` | Reference image vectors and their landmark mappings. |
| Optional scoring configuration | Compatible `calibration.json` | Supports calibrated scoring when it matches the model/index configuration. |

> **Recognition score:** Raw similarity scoring is not equivalent to a verified probability of correctness.

Backend ML configurations can be placed in a `.env.ml` file. Other configurations for the app are loaded from the backend's .env file. The place components also support a `.env.geoapify` file. These private configuration files should be kept separate from any front end environment files.

When using an S3-compatible image storage configuration the following settings should be provided: `S3_BUCKET`, AWS credentials and region, and `S3_ENDPOINT_URL` if required by the S3 provider. This is optional as storage in the database is also supported without a bucket.

---

## Frontend URLs used for the backend

The front end communicates with the backend to perform landmark recognition and obtain data for travel planning. By default the front end is expecting to find the backend on the same server as the browser address bar but on a different port (8000).

For example if the front end is being accessed at [http://localhost:5173/](http://localhost:5173/) then it is expecting to find the backend at [http://localhost:8000/](http://localhost:8000/)

This default server URL can be overridden using an environment variable. See [Frontend configuration](#frontend-configuration) for more information.

For local development it is recommended that the same hostname is used for both the frontend and backend, on their respective ports so that traveler cookies can function properly. The server needs to allow the origin of the browser. The full origin (including port and protocol) of the frontend needs to be included in the list of allowed origins for the server. If your server is using a LAN hostname, IP address or a different port then this must be configured if it is not already configured.

---

## Frontend integration with backend

After an image of a landmark is uploaded to the app the following steps occur:

1. The React app uploads the image to the /api/predict endpoint on the FastAPI backend
2. The backend creates an embedding of the image and searches the FAISS index for a matching image
3. If a matching image is accepted the backend can then look up the landmark information including coordinates in Neon and search for nearby places. If the image does not match an accepted image then the result is returned as unknown.
4. The backend returns JSON data to the React app
5. The React app uses the `destinationData.js` adapter to convert the returned data into destination data
6. The React app updates the destination preview and Trip Canvas areas

The featured destination selector also uses data obtained from the back end including landmark coordinates

The HotelResults and RestaurantResults components can also make requests for place search results directly to the backend. The AirportResults component makes requests to a separate endpoint on the backend for information about nearby airports.

There are separate routes on the backend for account creation, authentication, saving and retrieving saved itineraries, deleting saved itineraries and signing out. Itinerary editing occurs in the front end and the edited itinerary is included when an itinerary is saved.

Itineraries are associated with a currently authenticated traveler and stored in Neon. There is no direct connection between the front end and Neon.

---

## Services used by Trekmark

| Service | Services provided |
| --- | --- |
| FastAPI backend | Recognition of landmarks via the ML implementation, access to landmark, account and itinerary data, access to place data for near-by hotels, restaurants and airports, account creation and login, submission of community submitted landmarks and storage of saved itineraries |
| ML model and FAISS index | Creation of embeddings for images and searching of reference images for matching landmark images |
| Neon database | Storage of data about landmarks including photos and coordinates, traveler accounts and saved itineraries |
| Geoapify Place API | Providing results for nearby hotels, restaurants and airports given a coordinate location |
| Wikimedia Commons API | Providing best effort photos for nearby hotels and restaurants based on a place name and location information |
| Google Maps links | Opening locations in Google Maps or directions to an airport via Google Maps |

Photos for hotels and restaurants are not equivalent to photos provided by Neon for landmarks. The availability of photos can limit the number of results returned.

---

## Run locally

In order to run the front end the backend must first be configured to enable the features used in the app.

The front end requires Node.js and npm. The back end requires a configured Python environment along with access to a Neon database, Geoapify API key and the ML model and index files.

### 1. Set up and start the backend

From a terminal at the root of the repository run the following commands for your platform.

#### Windows — PowerShell

If a virtual environment has not already been created run the following commands:

```powershell
cd backend-integration
python -m venv .venv
```

Install required Python packages and start server using Python from the created environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

#### Mac — Terminal

If a virtual environment has not already been created run the following commands:

```bash
cd backend-integration
python3.12 -m venv .venv-mac
```

Activate the environment, install required packages and start server using Python from the created environment:

```bash
source .venv-mac/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

The Mac commands above assume Python 3.12 is installed. If a virtual environment already exists, first enter `backend-integration`, then skip its creation and use the commands for that environment to start the server.

Backend API documentation can be viewed at [http://localhost:8000/docs](http://localhost:8000/docs).

The back end requires several private configuration settings including a `DATABASE_URL` for connecting to Neon and a `GEOAPIFY_API_KEY` for accessing Geoapify. These settings can be provided either as environment variables or in a .env configuration file used by the back end. Administrator credentials are also provided on the back end.

For image recognition to work `DEMO_MODE` must be set to `false` and backend ML settings must contain valid model/index paths. Credentials and service keys should not be placed in any frontend code or in public documentation.

### 2. Start the frontend

From another terminal opened at the root of this Git repository:

```bash
cd frontend
npm ci
npm run dev
```

`npm ci` installs the exact dependencies from `package-lock.json`. Use this command by default unless changing dependencies.

When intentionally changing dependencies, use `npm install` and keep the resulting changes to `package.json` and `package-lock.json` together. It installs versions allowed by the dependency ranges; it does not necessarily install the latest release of every package.

Open the URL printed in the terminal by Vite, normally [http://localhost:5173/](http://localhost:5173/).

Keep the backend terminal running while using integrated features.

### 3. Build and preview the frontend

From the `frontend` folder:

```bash
npm run build
npm run preview
```

The build is written to `dist/`. Preview serves the built frontend locally; the backend must still be running and reachable.

See the [Vite guide](https://vite.dev/guide/) for more information about development and build commands.

---

## Frontend configuration

To specify a URL other than the default backend address, create a file named `.env.local` in the `frontend` folder, alongside `package.json`.

For a local backend, use:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
```

Replace this value with the backend's full URL, including the protocol and port where applicable. Restart Vite after changing the file. For a production build, set the value before running `npm run build`.

Any value beginning with `VITE_` can be accessed by browser-side JavaScript. Do not place passwords, database credentials, or private API keys in these variables.

If the frontend runs on a different hostname or port, add its full origin to the backend's `FRONTEND_ORIGINS` configuration. This is necessary to avoid cross-origin resource sharing (CORS) errors. For example, a frontend using port `5174` needs that origin allowed even if port `5173` is already configured.

Local development uses HTTP by default. Public HTTPS deployment requires appropriate hosting or reverse-proxy configuration, a reachable backend URL, and matching allowed origins.

## Other notes about using destinationData.js as an adapter

The current adapter converts the FastAPI backend's JSON response into the destination format used by the frontend. Keep it connected to the real response data rather than forcing uploaded images to use a predetermined landmark ID.

Featured destination mappings are still needed for preset selections. They should not replace the ML result for an uploaded image.

The image recognition request and adapter must agree on the response fields for the landmark name, location, coordinates, photos, and recognition score.

## Changing files where paths are expected

Use the path format expected by the relevant tool or configuration. Forward slashes are appropriate for URLs, JavaScript imports, and the model/index path examples. Windows terminal commands can use backslashes, as shown in the backend commands above.

---

## Known problems and future work

- Improve the accuracy of similarity recognition by the ML model and evaluate matching criteria for “unknown” results.
- A similarity score expressed as a percentage is not a verified probability that the landmark is correct.
- Improve itinerary selection criteria. The initial three-day itinerary is a template with no route optimization.
- Hotel and restaurant results depend on available photos; fewer than three cards may appear.
- Only geographic distances are provided, rather than walking or driving time estimates.
- Live flight pricing, hotel availability, and booking services are not integrated. Illustrative prices and travel estimates remain demo content.
- Saved itineraries are supported; a personal history of every uploaded recognition image is not implemented.
- Adding or modifying a landmark record does not automatically add corresponding images to the ML index. Index updates are a separate process.

## Notes for developers and capstone presentations

Code comments describe the major components, their purpose, dependencies, data flow, and relation to supporting services. They support development, code review, and capstone presentations.

The application includes working backend integrations alongside the prototype features and future work described above.
