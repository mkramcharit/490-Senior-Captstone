# Trekmark Frontend

A React-based travel planning application using images.

[Project overview and complete setup](../README.md) · [Backend](../backend/) · [Demo video](../assets/demo/TrekMark-Demo.mp4)

## Run locally

First, please check out the [root README's local setup instructions](../README.md#local-setup) to set up the API key, model files, database, and backend. The backend code is located in `backend/`.

From the root project directory in a new terminal:

```bash
cd frontend
npm ci
npm run dev
```

A URL will be printed out (typically [http://localhost:5173/](http://localhost:5173/)) - open this in your browser. When using features that require a connected backend, make sure to keep the backend running on port 8000.

On subsequent runs, simply navigate to `frontend/` and run `npm run dev`. When switching machines or updating the lockfile (`package-lock.json`), please run `npm ci` again.

## Main files

All paths listed below are relative to `frontend/`.

| File | Purpose |
| --- | --- |
| [`src/main.jsx`](src/main.jsx) | Overall React app, Trip Canvas, destination discovery, recognition feedback, and uploads. |
| [`src/destinationData.js`](src/destinationData.js) | Transforms destination data from the backend into something usable in the app, converting popular destination choices into preset IDs. |
| [`src/AccountPanel.jsx`](src/AccountPanel.jsx) | Traveler accounts, editing itineraries, saving itineraries, and using shared account features. |
| [`src/AdminPage.jsx`](src/AdminPage.jsx) | Logging in as an administrator and reviewing community submissions. |
| [`src/AirportResults.jsx`](src/AirportResults.jsx) | Information regarding the closest airport and how to get there. |
| [`src/HotelResults.jsx`](src/HotelResults.jsx) | Cards and photos of the closest hotels, along with search functionality. |
| [`src/RestaurantResults.jsx`](src/RestaurantResults.jsx) | Cards and photos of the closest restaurants, along with search functionality. |
| [`src/styles.css`](src/styles.css) | Overall styling, layout, responsiveness, and animations for the app. |
| [`src/hotels.css`](src/hotels.css) | Shared styling between restaurant and hotel results. |
| [`index.html`](index.html) | Vite and React entry point. |
| [`package.json`](package.json) | Lists dependencies and available npm scripts for the frontend. |
| [`package-lock.json`](package-lock.json) | Used by `npm ci` to ensure consistent installs. |

## User workflow

1. Choose a destination either by selecting one from a gallery or by uploading a landmark image.
2. See the confirmed destination, photos of that destination in the database, and nearby landmarks.
3. Use navigation to see information about the closest hotel, restaurant, and airport.
4. Log in to save the three-day itinerary after editing it.
5. Access previously saved itineraries via the traveler account section.

Community members can upload a landmark image along with its location. Administrators can view, modify, approve, reject, or delete these submissions.

## Backend connection

Data is sent to FastAPI as JSON or as an image file. The backend is responsible for handling accounts, external travel integration, database interactions, private API keys, and recognition.

By default, the frontend connects to the same hostname as the website on port 8000. To change this connection, please create a file at `frontend/.env.local`:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
```

After making this change, restart Vite. Use the same hostname for both the frontend and the backend (both should be `localhost`, for example), and make sure the backend includes the frontend’s origin in its `FRONTEND_ORIGINS` variable.

Any value that begins with `VITE_` will be accessible in the browser. Store administrator passwords, Geoapify keys, and database credentials in the private portion of the backend configuration.

## Images and recognition feedback

- Backed images are pulled from the database via the backend.
- Using Wikimedia Commons via the backend, images for restaurants and hotels are provided (with credit given).
- Recognition yields a matching score (rather than a calibrated accuracy estimate).
- If no match is found or a low score is returned, the user won’t be able to open the destination. In the event of a failed connection to the backend, users will receive feedback about attempting the request again.
- Due to a lack of available images, there may be less than three results when performing a search for nearby locations.

## Build commands

From `frontend/`:

```bash
npm run build
npm run preview
```

Running `npm run build` will generate a build that will be placed in `dist/`. Running `npm run preview` will serve this build locally for viewing; no backend will be launched or configured for a production environment.

For more details regarding model files, API endpoints, roles involved in this project, and limitations, please check out the [root README](../README.md).
