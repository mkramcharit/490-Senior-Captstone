# Trekmark Frontend - Commented Capstone Version

This folder contains the current Trekmark frontend with many comments.

## Files

### `src/main.jsx`

The main Trekmark React app. The following components are present in
this file:

-   preset destinations
-   rotating gallery of destinations
-   animated background particles
-   rotating globe/map
-   upload demo
-   destination preview card
-   Trip Canvas
-   3-day itinerary
-   fixed navigation
-   animated travel background

The comments are written in a style that is appropriate for a college
student. This is so that this file can be used for documentation, code
review, studying, and presenting the project during a capstone.

### `src/styles.css`

Most of the visual elements present in Trekmark are found in this file
including:

-   colors
-   spacing
-   responsive layouts
-   globe
-   cards
-   image gallery
-   Trip Canvas
-   fixed navigation
-   sunset background
-   animated flight transitions
-   animations

There is a lot of code in the stylesheet because the style has undergone
many iterations. Later CSS rules can override earlier ones. Comments
describe the significant iterations and current state.

### `index.html`

A small HTML file provided by Vite. React will be inserted into the
`<div id="root"></div>` element.

### `package.json`

Contains package dependencies and the commands for running and building
the app.

Technically, JSON does not support comments. For this reason,
`package.json` is intentionally unmarked with comments to ensure
npm/Vite can read it properly.

## Run the site

From within the Trekmark project directory:

``` bash
npm install
npm run dev
```

Navigate to the local address that is printed in the terminal by Vite.
Typically this is:

``` text
http://localhost:5173/
```

## Current prototype limitation

There is currently no backend. Prices, confidence scores, travel
recommendations, itinerary details and image recognition are all
prototype/mock data. The frontend is structured to allow these values to
be replaced later by data from the FastAPI backend.
