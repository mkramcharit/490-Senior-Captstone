


/*
TREKMARK FRONT END - main.jsx

This file contains the majority of React functionality for the present
Trekmark prototype.

The objective of the prototype is:

1. Enable a user to find a destination either by selecting a destination
   from a globe, or by uploading an image.
2. Show a preview card for a destination.
3. Allow user to fill out a more specific "Trip Canvas" with an example of
   flight, hotel, food, activities, pricing and itinerary for a destination.
4. Keep the design highly visual and provide a travel product experience,
   rather than a technical capstone/research project.
*/
import React, { useEffect, useMemo, useRef, useState } from 'react';

// React 18+ uses createRoot to attach the app to index.html
import { createRoot } from 'react-dom/client';


// Framer Motion is used for smooth transitions on fade in/out and sliding.
// AnimatePresence is helpful when removing elements because CSS has very little
// support for animating elements after they are removed by React.
import { AnimatePresence, motion } from 'framer-motion';
import {
  ArrowRight,
  Camera,
  ChevronDown,
  Compass,
  Hotel,
  MapPin,
  Plane,
  Search,
  Sparkles,
  Star,
  UtensilsCrossed,
  X,
  Zap,
} from 'lucide-react';


// Styling, responsive design, globe styling, background animation, fixed
// navigation bar and Trip Canvas layout are all defined here.
import './styles.css';


// In dev the FastAPI server is running independently of the Vite frontend.
// All landmark recognition requests are sent to this server.
const API_BASE_URL = 'http://127.0.0.1:8000';


/*
PRESET GLOBE DESTINATIONS

There are currently 5 destinations on the globe.

Each of these has the following properties:

- id: React internal id
- name/country: displayed in UI
- lat/lng: the real lat/lng to use for a map pin
- kicker: short promotional copy
- confidence: fake confidence for landmark recognition (only in prototype)
- hero / experienceImage / stayImage / eatImage: individual images for use in
  the Trip Canvas (so that the Trip Canvas does not reuse an image)
- hotel / restaurant / attraction: example of these three types of experiences
- stayPrice / eatPrice / doPrice / flight: examples of the price for each type
  of experience

Once the backend exists, the majority of this data will be provided by the API
rather than hardcoded in this file.

Having this list of pre-defined destinations in one place makes the rest of the
frontend much easier to use. Rather than hardcoding Orlando, Tokyo, Paris, etc.,
in 5 different places, React can loop over this data and use it in multiple
places. This is cleaner and should also make integration with the backend easier.
We can replace the mock data with API data.
*/
const destinations = [
  {
    id: 'orlando', name: 'Orlando', country: 'Florida, USA', lat: 28.5383, lng: -81.3792,
    kicker: 'Theme parks · sunshine · easy escapes', confidence: 98,
    hero: 'https://images.unsplash.com/photo-1533107862482-0e6974b06ec4?auto=format&fit=crop&w=1600&q=90',
    experienceImage: 'https://images.unsplash.com/photo-1500916434205-0c77489c6cf7?auto=format&fit=crop&w=1400&q=90',
    stayImage: 'https://images.unsplash.com/photo-1582719508461-905c673771fd?auto=format&fit=crop&w=1200&q=90',
    eatImage: 'https://images.unsplash.com/photo-1552566626-52f8b828add9?auto=format&fit=crop&w=1200&q=90',
    summary: 'An energy-packed escape built around immersive lands, headline rides, resort nights and easy weekend momentum.',
    hotel: 'Universal Helios Grand Hotel', stayPrice: '$349 / night',
    restaurant: 'The Ravenous Pig', eatPrice: '$28 avg meal',
    attraction: 'Epic Universe', doPrice: '$159 ticket',
    flight: '$146 round trip'
  },
  {
    id: 'tokyo', name: 'Tokyo', country: 'Japan', lat: 35.6762, lng: 139.6503,
    kicker: 'Neon nights · ramen · quiet temples', confidence: 99,
    hero: 'https://images.unsplash.com/photo-1540959733332-eab4deabeeaf?auto=format&fit=crop&w=1600&q=90',
    experienceImage: 'https://images.unsplash.com/photo-1528360983277-13d401cdc186?auto=format&fit=crop&w=1400&q=90',
    stayImage: 'https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=1200&q=90',
    eatImage: 'https://images.unsplash.com/photo-1559339352-11d035aa65de?auto=format&fit=crop&w=1200&q=90',
    summary: 'A city that can feel futuristic, traditional, electric and calm in the same afternoon.',
    hotel: 'Shinjuku Granbell', stayPrice: '$214 / night',
    restaurant: 'Sushi Tokyo Ten', eatPrice: '$35 avg meal',
    attraction: 'Senso-ji', doPrice: '$12 local transit + entry area',
    flight: '$842 round trip'
  },
  {
    id: 'paris', name: 'Paris', country: 'France', lat: 48.8566, lng: 2.3522,
    kicker: 'Art · cafés · iconic streets', confidence: 97,
    hero: 'https://images.unsplash.com/photo-1502602898657-3e91760cbb34?auto=format&fit=crop&w=1600&q=90',
    experienceImage: 'https://images.unsplash.com/photo-1499856871958-5b9627545d1a?auto=format&fit=crop&w=1400&q=90',
    stayImage: 'https://images.unsplash.com/photo-1445019980597-93fa8acb246c?auto=format&fit=crop&w=1200&q=90',
    eatImage: 'https://images.unsplash.com/photo-1559329007-40df8a9345d8?auto=format&fit=crop&w=1200&q=90',
    summary: 'Landmarks you already know, neighborhoods you do not, and a city built for wandering slowly.',
    hotel: 'Hôtel Dame des Arts', stayPrice: '$298 / night',
    restaurant: 'Bouillon République', eatPrice: '$42 avg meal',
    attraction: 'Eiffel Tower', doPrice: '$31 ticket',
    flight: '$612 round trip'
  },
  {
    id: 'amazon', name: 'Amazon Rainforest', country: 'Brazil', lat: -3.4653, lng: -62.2159,
    kicker: 'Wildlife · rivers · immersive nature', confidence: 94,
    hero: 'https://images.unsplash.com/photo-1516026672322-bc52d61a55d5?auto=format&fit=crop&w=1600&q=90',
    experienceImage: 'https://images.unsplash.com/photo-1465379944081-7f47de8d74ac?auto=format&fit=crop&w=1400&q=90',
    stayImage: 'https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=1200&q=90',
    eatImage: 'https://images.unsplash.com/photo-1467003909585-2f8a72700288?auto=format&fit=crop&w=1200&q=90',
    summary: 'A deeper kind of trip—river routes, layered green horizons and wildlife beyond the city grid.',
    hotel: 'Juma Amazon Lodge', stayPrice: '$420 / night',
    restaurant: 'Floating River Kitchen', eatPrice: '$24 avg meal',
    attraction: 'Rio Negro Expedition', doPrice: '$95 excursion',
    flight: '$718 round trip'
  },
  {
    id: 'rio', name: 'Rio de Janeiro', country: 'Brazil', lat: -22.9068, lng: -43.1729,
    kicker: 'Beaches · mountains · nightlife', confidence: 96,
    hero: 'https://images.unsplash.com/photo-1483729558449-99ef09a8c325?auto=format&fit=crop&w=1600&q=90',
    experienceImage: 'https://images.unsplash.com/photo-1606141923451-000827e3c16e?auto=format&fit=crop&w=1600&q=90',
    stayImage: 'https://images.unsplash.com/photo-1522798514-97ceb8c4f1c8?auto=format&fit=crop&w=1200&q=90',
    eatImage: 'https://images.unsplash.com/photo-1514933651103-005eec06c04b?auto=format&fit=crop&w=1200&q=90',
    summary: 'Oceanfront energy, dramatic peaks and a city that feels cinematic from almost every angle.',
    hotel: 'Arena Copacabana', stayPrice: '$226 / night',
    restaurant: 'Aprazível', eatPrice: '$30 avg meal',
    attraction: 'Christ the Redeemer', doPrice: '$18 ticket',
    flight: '$684 round trip'
  }
];


/*
ROTATING DESTINATION GALLERY

This is the large horizontal image gallery found lower in the application.

There are 5 pre-defined destinations on the globe but some of the gallery images
have a "trip" object associated with them. This allows the user to select
"Plan this trip" on one of these images and use the same Trip Canvas that is
used for the globe.

For Tokyo and the Amazon, we reuse an existing destination object using
destinations.find(...). No duplicate data is created.

The gallery is set up similarly to the globe using data. Some items have their
own trip object while others reuse an existing destination using .find().
Again, reusing an object here prevents copying data across the page. If we were
to copy/paste data across the page it would quickly get messy.
*/
const gallery = [
  {
    title: 'New York after dark',
    image: 'https://images.unsplash.com/photo-1485871981521-5b1fd3805eee?auto=format&fit=crop&w=1800&q=90',
    trip: {
      id: 'new-york', name: 'New York City', country: 'New York, USA',
      kicker: 'Skyline · neighborhoods · late nights', confidence: 99,
      hero: 'https://images.unsplash.com/photo-1485871981521-5b1fd3805eee?auto=format&fit=crop&w=1800&q=90',
      experienceImage: 'https://images.unsplash.com/photo-1479839672679-a46483c0e7c8?auto=format&fit=crop&w=1400&q=90',
      stayImage: 'https://images.unsplash.com/photo-1520250497591-112f2f40a3f4?auto=format&fit=crop&w=1200&q=90',
      eatImage: 'https://images.unsplash.com/photo-1552566626-52f8b828add9?auto=format&fit=crop&w=1200&q=90',
      summary: 'Iconic skyline views, neighborhood energy and more to do than a single weekend can hold.',
      hotel: 'Arlo Midtown', stayPrice: '$312 / night',
      restaurant: 'Ci Siamo', eatPrice: '$45 avg meal',
      attraction: 'Top of the Rock', doPrice: '$44 ticket',
      flight: '$188 round trip'
    }
  },
  {
    title: 'Tokyo electric',
    image: 'https://images.unsplash.com/photo-1519501025264-65ba15a82390?auto=format&fit=crop&w=1800&q=90',
    trip: destinations.find(d => d.id === 'tokyo')
  },
  {
    title: 'The Great Wall',
    image: 'https://images.unsplash.com/photo-1508804185872-d7badad00f7d?auto=format&fit=crop&w=1800&q=90',
    trip: {
      id: 'great-wall', name: 'The Great Wall', country: 'Beijing, China',
      kicker: 'History · mountain views · day trips', confidence: 98,
      hero: 'https://images.unsplash.com/photo-1508804185872-d7badad00f7d?auto=format&fit=crop&w=1800&q=90',
      experienceImage: 'https://images.unsplash.com/photo-1578271887552-5ac3a72752bc?auto=format&fit=crop&w=1400&q=90',
      stayImage: 'https://images.unsplash.com/photo-1455587734955-081b22074882?auto=format&fit=crop&w=1200&q=90',
      eatImage: 'https://images.unsplash.com/photo-1526318896980-cf78c088247c?auto=format&fit=crop&w=1200&q=90',
      summary: 'A landmark-scale trip combining Beijing culture with one of the world’s most recognizable landscapes.',
      hotel: 'The Orchid Beijing', stayPrice: '$168 / night',
      restaurant: 'TRB Hutong', eatPrice: '$36 avg meal',
      attraction: 'Mutianyu Great Wall', doPrice: '$9 ticket',
      flight: '$936 round trip'
    }
  },
  {
    title: 'Into the green',
    image: 'https://images.unsplash.com/photo-1448375240586-882707db888b?auto=format&fit=crop&w=1800&q=90',
    trip: destinations.find(d => d.id === 'amazon')
  },
  {
    title: 'Amalfi light',
    image: 'https://images.unsplash.com/photo-1533104816931-20fa691ff6ca?auto=format&fit=crop&w=1800&q=90',
    trip: {
      id: 'amalfi', name: 'Amalfi Coast', country: 'Campania, Italy',
      kicker: 'Cliffside towns · sea views · slow days', confidence: 97,
      hero: 'https://images.unsplash.com/photo-1533104816931-20fa691ff6ca?auto=format&fit=crop&w=1800&q=90',
      experienceImage: 'https://images.unsplash.com/photo-1500375592092-40eb2168fd21?auto=format&fit=crop&w=1400&q=90',
      stayImage: 'https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=1200&q=90',
      eatImage: 'https://images.unsplash.com/photo-1514933651103-005eec06c04b?auto=format&fit=crop&w=1200&q=90',
      summary: 'A coastal escape built around dramatic views, small towns, long lunches and time near the water.',
      hotel: 'Hotel Marina Riviera', stayPrice: '$410 / night',
      restaurant: 'Da Gemma', eatPrice: '$55 avg meal',
      attraction: 'Path of the Gods', doPrice: '$0 trail access',
      flight: '$704 round trip'
    }
  },
];


/*
BACKGROUND PARTICLES

These are the small animated particles in the background.

Each of these has a random position, size, delay and duration. One randomization
happens at initialization. useMemo is used here so that the particles do not
jump to new random positions when the page re-renders because of React.

This is mostly visual and does go a long way towards providing a dynamic page
instead of a completely static mock-up. The animation is kept lightweight since
there is no real benefit to cooking the GPU for a small number of animated
background particles.
*/
function ParticleField() {
  const particles = useMemo(() => Array.from({ length: 34 }, (_, i) => ({
    id: i, left: `${Math.random() * 100}%`, top: `${Math.random() * 100}%`,
    size: 1 + Math.random() * 3, delay: Math.random() * 9, duration: 8 + Math.random() * 14,
  })), []);
  return <div className="particle-field" aria-hidden="true">{particles.map(p => <span key={p.id} style={{left:p.left, top:p.top, width:p.size, height:p.size, animationDelay:`-${p.delay}s`, animationDuration:`${p.duration}s`}} />)}</div>;
}


/*
LIGHTWEIGHT "GLOBE" COMPONENT

The current implementation of the globe is optimized for performance.

Rather than warping a high resolution map texture in JavaScript multiple times,
we instead are shifting copies of a real world map texture inside of a circular
view. The location pins are drawn inside of the same map texture. Because both
the map and location pins are moving together, the pins will always be in the
correct geographic location.

This allows for:

- A rotating globe that looks like earth
- Correctly positioned continents
- Pins that stay in the correct location on the map
- Much lower latency than our previous canvas warping implementations.

Props:

- selected: currently selected location
- onSelect: called on click of a location pin

The globe is somewhat complex, but the concept behind it is relatively simple.
A map and all of the location pins can flow inside a circular view. This prevents
any pin from drifting and allows for a rotating Earth while not requiring a much
heavier 3D globe library.
*/
function CanvasGlobe({ selected, onSelect }) {
  
  // Reference to the circular view that crops the map.
  const viewportRef = useRef(null);

  
  
  // Several copies of the entire world map are created so that the map can loop
  // infinitely without whitespace at either end.
  const worldRefs = useRef([]);

  
  
  // Current longitude/rotation value. Instead of using state, we use refs because
  // this gets updated every animation frame and should not trigger a React re-render.
  const rotationRef = useRef(-28);

  
  
  // The longitude we smoothy rotate to after a destination is selected.
  const targetRotationRef = useRef(null);

  
  
  // Slows automatic rotation for a short time after a destination is selected.
  // This gives the user time to check out the selected destination.
  const pauseUntilRef = useRef(0);

  
  // Stores requestAnimationFrame to be cancelled later on in the cleanup.
  const rafRef = useRef(null);

  
  
  // Used to calculate how long has passed since the last animation frame.
  // This allows the animation to be smooth on 60 Hz, 120 Hz and 144 Hz displays.
  const lastTimeRef = useRef(performance.now());

  
  
  // To select a destination cause the globe to rotate to the longitude of the new
  // destination and pause the automatic rotation for 2.6 seconds.
  useEffect(() => {
    if (!selected) return;
    targetRotationRef.current = selected.lng;
    pauseUntilRef.current = performance.now() + 2600;
  }, [selected]);

  
  
  
  // The animation loop used for the globe.
  // Runs once on initialization of the globe and is removed when the component is removed.
  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;

    const update = (now) => {
      const dt = Math.min(40, now - lastTimeRef.current);
      lastTimeRef.current = now;

      if (targetRotationRef.current !== null) {
        let diff = targetRotationRef.current - rotationRef.current;
        diff = ((diff + 540) % 360) - 180;
        rotationRef.current += diff * Math.min(.17, dt * .0047);

        if (Math.abs(diff) < .15) {
          rotationRef.current = targetRotationRef.current;
          targetRotationRef.current = null;
        }
      } else if (now > pauseUntilRef.current) {
        rotationRef.current = (rotationRef.current + dt * .0048) % 360;
      }

      // 560 is a fallback in case the browser has not completed measuring the globe yet.
      // This prevents the first animation frame from doing some odd calculations while
      // the layout is still settling.
      const viewportWidth = viewport.clientWidth || 560;
      const worldWidth = viewportWidth * 2;

      
      // Center the current/selected longitude in the circular view.
      const normalizedRotation =
        ((rotationRef.current + 180) % 360 + 360) % 360;

      const centerOnTrack =
        (normalizedRotation / 360) * worldWidth;

      const translateX =
        viewportWidth / 2 - centerOnTrack;

      
      
      
      // The pins are inside the world maps.
      // The world map and pins are translated together so that the labels remain in
      // their correct geolocation.
      //
      // Each copy of the world map has the same value for translation. This is what
      // makes the looping texture appear as one globe instead of three separate
      // copies of the world moving independently.
      worldRefs.current.forEach((world) => {
        if (world) {
          world.style.transform = `translate3d(${translateX}px,0,0)`;
        }
      });

      rafRef.current = requestAnimationFrame(update);
    };

    rafRef.current = requestAnimationFrame(update);

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  
  
  // A function that creates a copy of a world map along with all of the destination
  // pins. Three copies are created to allow for infinite looping.
  const renderWorldCopy = (copyKey, leftPercent, refIndex) => (
    <div
      key={copyKey}
      ref={(el) => { worldRefs.current[refIndex] = el; }}
      className="locked-world"
      style={{ left: leftPercent }}
    >
      <div className="locked-world__texture" />

      {destinations.map((d) => {
        
        
        
        
        
        
        
        
        // Converts a pair of lat/lng to percentage values on an equirectangular world map.
        //
        // Longitude: -180 degrees is far left and +180 degrees is far right.
        //
        // Latitude: +90 degrees is on top (North Pole) and -90 degrees is on bottom.
        const x = ((d.lng + 180) / 360) * 100;
        const y = ((90 - d.lat) / 180) * 100;

        return (
          <button
            key={`${copyKey}-${d.id}`}
            className={`locked-marker ${selected?.id === d.id ? 'active' : ''}`}
            style={{ left: `${x}%`, top: `${y}%` }}
            onClick={() => onSelect(d)}
            aria-label={`Select ${d.name}`}
          >
            <span className="locked-marker__dot" />
            <span className="locked-marker__stem" />
            <span className="locked-marker__card">
              <strong>{d.name}</strong>
              <small>{d.country}</small>
            </span>
          </button>
        );
      })}
    </div>
  );

  return (
    <div className="locked-earth-shell">
      <div ref={viewportRef} className="locked-earth">
        {renderWorldCopy('prev', '-200%', 0)}
        {renderWorldCopy('main', '0%', 1)}
        {renderWorldCopy('next', '200%', 2)}

        <div className="locked-earth__lighting" />
        <div className="locked-earth__atmosphere" />
      </div>
    </div>
  );
}


/*
MAIN TREKMARK APPLICATION

App() creates the visible page components and assembles the components of the
page. The majority of the page is currently a single page app. As a user
progresses through the app, clicking on links will cause changes to React state
rather than switching to a different HTML page.

App() is essentially in charge of handling page state. It keeps track of the
current selected destination, visibility of the detailed Trekmark Trip Canvas,
the currently uploaded image (temporary URL), visibility of the fake AI image
processing page and the currently displayed image in the rotating gallery.
*/
function App() {
  
  
  // Hidden input for image uploads. Used by several buttons in the app to allow a
  // user to upload a file using the user's default file opener.
  const fileRef = useRef();

  
  // Currently selected destination. If this is null then no destination is selected.
  const [selected, setSelected] = useState(null);

  
  // Boolean to show or hide detailed Trekmark Trip Canvas
  const [detailOpen, setDetailOpen] = useState(false);

  
  // Temporary URL for the currently uploaded image
  const [uploadPreview, setUploadPreview] = useState(null);

  
  // Boolean to show or hide the fake AI image processing page
  const [analyzing, setAnalyzing] = useState(false);

  
  // Currently displayed image in the rotating gallery
  const [galleryIndex, setGalleryIndex] = useState(0);

  // Tracks form used by user to submit a landmark.
  const [submissionStatus, setSubmissionStatus] = useState('');
  const [submissionImageUrl, setSubmissionImageUrl] = useState('');

  
  
  
  // Advances cinematic destination gallery every 5.2 seconds.
  // Will cancel interval on component cleanup.
  useEffect(() => {
    const t = setInterval(
      () => setGalleryIndex(i => (i + 1) % gallery.length),
      5200
    );
    return () => clearInterval(t);
  }, []);

  
  
  
  // Called when clicking on a location on the globe. Selects the destination,
  // hides any existing planner and scrolls down to the destination preview card.
  //
  // We use a timeout to give React time to render the new destination preview
  // card before we scroll to it. We sometimes scroll too early and end up in an
  // awkward position. This is lowkey annoying.
  const focusDestination = (d) => {
    setSelected(d);
    setDetailOpen(false);

    window.setTimeout(() => {
      document.querySelector('#discover')?.scrollIntoView({
        behavior: 'smooth',
        block: 'center'
      });
    }, 500);
  };

  
  
  // Deselects the currently selected destination, hides the destination preview
  // card and returns the user to exploring the globe.
  const clearDestination = () => {
    setSelected(null);
    setDetailOpen(false);
    window.setTimeout(() => {
      document.querySelector('#top')?.scrollIntoView({
        behavior: 'smooth',
        block: 'start'
      });
    }, 80);
  };

  
  
  // Opens the Trip Canvas for the currently displayed destination in the cinematic
  // destination gallery. This gives the gallery a use and is not completely decorative.
  const planGalleryTrip = () => {
    const trip = gallery[galleryIndex]?.trip;
    if (!trip) return;
    setSelected(trip);
    setDetailOpen(true);
    window.setTimeout(() => {
      document.querySelector('#planner')?.scrollIntoView({
        behavior: 'smooth',
        block: 'start'
      });
    }, 120);
  };

  
  
  
  // Add the four prototype images to the Trip Canvas.
  // Individual image inputs are used rather than repeating an image because it
  // would be uninteresting to a travel planner.
  //
  // By creating this array upfront the JSX becomes much cleaner. Rather than having
  // to create four almost identical image components manually, we define the data
  // once and then use .map() to repeat the components.
  const plannerVisuals = selected ? [
    {
      kind: 'Destination view',
      title: selected.name,
      image: selected.hero,
      className: 'planner-visual planner-visual--hero'
    },
    {
      kind: 'Stay',
      title: selected.hotel,
      image: selected.stayImage || 'https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=1200&q=90',
      className: 'planner-visual'
    },
    {
      kind: 'Eat',
      title: selected.restaurant,
      image: selected.eatImage || 'https://images.unsplash.com/photo-1414235077428-338989a2e8c0?auto=format&fit=crop&w=1200&q=90',
      className: 'planner-visual'
    },
    {
      kind: 'Experience',
      title: selected.attraction,
      image: selected.experienceImage || selected.hero,
      className: 'planner-visual planner-visual--wide'
    }
  ] : [];

  
  
  
  
  
  
  
  
  
  
  
  // Image upload flow.
  //
  // The old prototype paused for 1.8 seconds and always selected Paris.
  // This version sends the selected image to the FastAPI /api/predict endpoint.
  //
  // Current flow:
  //
  // 1. Read selected image file.
  // 2. Generate a local preview for the scanning screen.
  // 3. Add the image to FormData.
  // 4. Send the image to FastAPI.
  // 5. FastAPI validates the image and returns a landmark id and confidence.
  // 6. FastAPI retrieves the matching landmark information from Neon.
  // 7. Convert the backend response into the same destination format already
  //    used throughout the frontend.
  // 8. Show the returned destination on the page.
  //
  // For the 60% checkpoint, only the ML recognition result is simulated.
  // The image upload, FastAPI request, Neon lookup and React state update are live.
  const onUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const previewUrl = URL.createObjectURL(file);

    setUploadPreview(previewUrl);
    setAnalyzing(true);
    setDetailOpen(false);

    const formData = new FormData();
    formData.append('file', file);

    // Keep the scanning animation visible long enough for the user to see it.
    // The backend request still starts immediately, but the result will not be
    // displayed until at least 2.5 seconds have passed.
    const minimumScanTime = new Promise((resolve) => {
      setTimeout(resolve, 2500);
    });

    try {
      const response = await fetch(`${API_BASE_URL}/api/predict`, {
        method: 'POST',
        body: formData,
      });

      await minimumScanTime;

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(
          errorData?.detail || 'Trekmark could not identify this image.'
        );
      }

      const data = await response.json();
      const landmark = data.landmark;

      // The current frontend already expects destination objects with fields such
      // as name, country, lat, lng, hero and confidence. The backend response is
      // converted here so the existing destination card and globe can reuse it.
      const backendDestination = {
        id: `landmark-${landmark.id}`,
        landmarkId: landmark.id,
        name: landmark.name,
        city: landmark.city,
        state: landmark.state,
        countryName: landmark.country,
        country: [
          landmark.city,
          landmark.state,
          landmark.country
        ].filter(Boolean).join(', '),
        lat: landmark.latitude,
        lng: landmark.longitude,
        confidence: Math.round(data.confidence * 100),
        hero: landmark.image || previewUrl,
        categoryName: landmark.category_name
          ? landmark.category_name
              .replace('Category:', '')
              .replaceAll('_', ' ')
          : 'Recognized landmark',
        kicker: landmark.category_name
          ? landmark.category_name
              .replace('Category:', '')
              .replaceAll('_', ' ')
          : 'Recognized landmark',
        summary:
          `Trekmark identified ${landmark.name} using the recognition pipeline and retrieved its location information from the live landmark database.`,
        experienceImage: landmark.image || previewUrl,
        stayImage: landmark.image || previewUrl,
        eatImage: landmark.image || previewUrl,
        hotel: 'Travel data coming next',
        stayPrice: '$—',
        restaurant: 'Restaurant data coming next',
        eatPrice: '$—',
        attraction: 'Nearby landmarks coming next',
        doPrice: '$—',
        flight: 'Flight data coming next',
        recognitionMode: data.recognition_mode,
        galleryImages: data.landmark_photos || [],
        nearbyLandmarks: data.nearby_landmarks || [],
      };

      setSelected(backendDestination);
      setDetailOpen(false);

      window.setTimeout(() => {
        document.querySelector('#discover')?.scrollIntoView({
          behavior: 'smooth',
          block: 'center'
        });
      }, 350);
    } catch (error) {
      console.error('Trekmark upload failed:', error);
      window.alert(
        error.message || 'Trekmark could not process the uploaded image.'
      );
    } finally {
      setAnalyzing(false);

      // Resetting the input lets the user select the exact same image again.
      e.target.value = '';
    }
  };

  // User landmark submission flow.
  //
  // The user can suggest a landmark for Trekmark by providing a landmark name,
  // image URL and country. City, state, latitude and longitude are optional
  // because not every landmark in the dataset has all of those values.
  //
  // The form is sent as multipart FormData so the backend can use the same
  // request style later when direct image uploads are connected to S3.
  const submitLandmark = async (e) => {
    e.preventDefault();

    // Store the form element before awaiting the backend response.
    // React's event currentTarget should not be relied on after an await.
    const formElement = e.currentTarget;
    const form = new FormData(formElement);

    setSubmissionStatus('submitting');

    const optionalFields = ['city', 'state', 'lat', 'lon'];

    optionalFields.forEach((field) => {
      if (!form.get(field)?.toString().trim()) {
        form.delete(field);
      }
    });

    try {
      const response = await fetch(`${API_BASE_URL}/submission`, {
        method: 'POST',
        body: form,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(
          errorData?.detail || 'Trekmark could not submit this landmark.'
        );
      }

      formElement.reset();
      setSubmissionImageUrl('');
      setSubmissionStatus('success');
    } catch (error) {
      console.error('Landmark submission failed:', error);
      setSubmissionStatus('error');
    }
  };

  // Returns the submission section to a blank form so the user can add
  // another landmark or retry after an unsuccessful submission.
  const resetSubmission = () => {
    setSubmissionImageUrl('');
    setSubmissionStatus('');
  };

  return (
    <>
      {


}
      {/*
        FIXED NAVIGATION

        Now stays fixed while scrolling so that the logo, "How it works", login and upload
        all remain accessible throughout the page.
      */}
      <nav className="nav nav-fixed">
        <div className="nav-inner shell">
          <a className="brand" href="#top"><span className="brand-mark"><Compass size={16}/></span>Trekmark</a>
          <div className="nav-links">
            <a href="#how">How it works</a>
            <button className="nav-login">Log in</button>
            <button className="upload-mini" onClick={() => fileRef.current?.click()}><Camera size={15}/> Upload photo</button>
          </div>
        </div>
      </nav>

      <main>
        {


}
        {/*
          TRAVEL BACKGROUND

          This section is purely decorative. The blend of sunsets, flight paths, moving
          planes and particles give the page a travel/discovery feel. aria-hidden prevents
          screen readers from interpreting this section as content.
        */}
        <div className="travel-bg" aria-hidden="true">
          <div className="travel-bg__sunset" />
          <div className="travel-bg__orb travel-bg__orb--one" />
          <div className="travel-bg__orb travel-bg__orb--two" />

          <div className="flight-map">
            {Array.from({ length: 8 }, (_, i) => (
              <div key={i} className={`flight-path flight-path--${i + 1}`}>
                <span className="flight-trail" />
                <Plane className="flight-plane" size={i % 3 === 0 ? 22 : 17} />
              </div>
            ))}
          </div>
        </div>

        <ParticleField />

      {


}
      {/*
        HERO / FIRST IMPRESSION

        Main copy and interactive world.
      */}
      <section className="hero shell" id="top">
        <motion.div className="hero-copy" initial={{opacity:0,y:28}} animate={{opacity:1,y:0}} transition={{duration:.8}}>
          <div className="eyebrow"><Sparkles size={14}/> AI-powered travel discovery</div>
          <h1>See a place.<br/><span>Know where it is.</span><br/>Plan the trip.</h1>
          <p>Trekmark turns a single photo into a destination you can explore—then helps shape the flights, stays, food and experiences around it so the moment inspiration hits, the trip already feels within reach.</p>
          <div className="hero-actions">
            <button className="primary" onClick={() => fileRef.current?.click()}><Camera size={18}/> Identify a photo</button>
            <button className="ghost" onClick={() => document.querySelector('#discover')?.scrollIntoView({behavior:'smooth'})}>Explore the globe <ArrowRight size={17}/></button>
          </div>
          <div className="micro-proof"><span><Zap size={14}/> Recognition</span><span>Confidence</span><span>Trip planning</span></div>
          <input ref={fileRef} onChange={onUpload} type="file" accept="image/*" hidden />
        </motion.div>

        <motion.div className="globe-stage" initial={{opacity:0,scale:.92}} animate={{opacity:1,scale:1}} transition={{duration:1.2, ease:[.16,1,.3,1]}}>
          <div className="globe-glow" />
          <CanvasGlobe selected={selected} onSelect={focusDestination} />
          <div className="globe-hint">
            <span className="globe-hint-pulse" />
            Select a glowing location on the globe
          </div>
        </motion.div>
      </section>

      {


}
      {/*
        PREVIEW OF SELECTED DESTINATION

        This is small by default until a destination is selected.
        When a destination is selected, this becomes the large image
        with buttons "Build this trip" and "See something else".
      */}
      <section className="selected-strip shell" id="discover">
        {/* mode="wait" causes Framer Motion to remove the previous card completely
            before animating the new one. This ensures a clean transition and avoids
            both destination cards being visible for a brief moment. */}
        <AnimatePresence mode="wait">
          {selected ? (
            <motion.div
              key={selected.id}
              className="selected-card"
              initial={{opacity:0,y:24,scale:.985}}
              animate={{opacity:1,y:0,scale:1}}
              exit={{opacity:0,y:-12,scale:.99}}
              transition={{duration:.55,ease:[.16,1,.3,1]}}
            >
              <div
                className="selected-image"
                style={{backgroundImage:`linear-gradient(90deg,rgba(4,7,11,.88),rgba(4,7,11,.08)),url(${selected.hero})`}}
              />
              <div className={`selected-copy ${selected.recognitionMode ? 'recognized-copy' : ''}`}>
                {selected.recognitionMode ? (
                  <>
                    {/*
                      RECOGNIZED LANDMARK RESULT

                      Uploaded images use this version of the destination card.
                      It makes the recognition result, confidence, location and
                      coordinates easy to see during the checkpoint demo.

                      Preset globe destinations continue to use the original
                      destination preview below.
                    */}
                    <div className="recognition-label">
                      <span className="recognition-dot" />
                      Recognized landmark
                    </div>

                    <h2>{selected.name}</h2>

                    <div className="recognition-location">
                      <MapPin size={16}/> {selected.country}
                    </div>

                    <div className="recognition-facts">
                      <div>
                        <span>Match confidence</span>
                        <strong>{selected.confidence}%</strong>
                      </div>
                      <div>
                        <span>Coordinates</span>
                        <strong>
                          {Number(selected.lat).toFixed(4)}, {Number(selected.lng).toFixed(4)}
                        </strong>
                      </div>
                    </div>

                    <div className="selected-actions">
                      <button
                        className="primary compact"
                        onClick={() => {
                          setDetailOpen(true);
                          setTimeout(() => document.querySelector('#planner')?.scrollIntoView({behavior:'smooth'}), 100);
                        }}
                      >
                        Build this trip <ArrowRight size={16}/>
                      </button>
                      <button className="ghost compact selected-reset" onClick={clearDestination}>
                        Scan another photo
                      </button>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="destination-meta">
                      <MapPin size={15}/> {selected.country}
                      <span>{selected.confidence}% match confidence</span>
                    </div>
                    <h2>{selected.name}</h2>
                    <p>{selected.kicker}</p>
                    <div className="selected-actions">
                      <button
                        className="primary compact"
                        onClick={() => {
                          setDetailOpen(true);
                          setTimeout(() => document.querySelector('#planner')?.scrollIntoView({behavior:'smooth'}), 100);
                        }}
                      >
                        Build this trip <ArrowRight size={16}/>
                      </button>
                      <button className="ghost compact selected-reset" onClick={clearDestination}>
                        See something else
                      </button>
                    </div>
                  </>
                )}
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="globe-prompt"
              className="selection-prompt"
              initial={{opacity:0}}
              animate={{opacity:1}}
              exit={{opacity:0}}
            >
              <span>Explore a preset destination</span>
              <strong>Choose one of the glowing points above to preview the Trekmark experience.</strong>
            </motion.div>
          )}
        </AnimatePresence>
      </section>

      {


}
      {/*
        CINEMATIC GALLERY OF DESTINATIONS

        Travel photos are automatically rotated. Users can also
        choose a travel photo and use it to plan a trip.
      */}
      <section className="visual-story" aria-label="Destination gallery">
        <AnimatePresence mode="wait">
          <motion.div key={galleryIndex} className="visual-bg" style={{backgroundImage:`linear-gradient(180deg,rgba(5,7,11,.08),rgba(5,7,11,.88)),url(${gallery[galleryIndex].image})`}} initial={{opacity:0,scale:1.035}} animate={{opacity:1,scale:1}} exit={{opacity:0}} transition={{duration:1.2}} />
        </AnimatePresence>
        <div className="shell visual-content">
          <div className="eyebrow light">For wherever curiosity takes you</div>
          <h2>{gallery[galleryIndex].title}</h2>
          <button className="gallery-plan" onClick={planGalleryTrip}>
            Plan this trip <ArrowRight size={17}/>
          </button>
          <div className="gallery-dots">{gallery.map((g,i)=><button key={g.title} className={i===galleryIndex?'active':''} onClick={()=>setGalleryIndex(i)} aria-label={`Show ${g.title}`}/>)}</div>
        </div>
      </section>

      {


}
      {/*
        HOW TREKMARK HELPS

        A brief marketing description of the Recognize -> Understand -> Go
        pipeline. Not written like a research paper.
      */}
      <section className="promise shell" id="how">
        <div className="eyebrow">One photo. One starting point.</div>
        <h2>Stop wondering where.<br/><span>Start wondering when.</span></h2>
        <p>Trekmark recognizes the place in front of you, shows how confident it is, then turns that answer into a trip you can actually picture yourself taking.</p>
        <div className="promise-grid">
          <div><Search/><h3>Recognize</h3><p>Upload the image. Trekmark finds the strongest visual match.</p></div>
          <div><Sparkles/><h3>Understand</h3><p>See the landmark, location and confidence without digging through metadata.</p></div>
          <div><Plane/><h3>Go</h3><p>Move directly into flights, hotels, restaurants and nearby experiences.</p></div>
        </div>
      </section>

      {


}
      {/*
        TREKMARK TRIP CANVAS

        Appears only when the user chooses to plan a trip.
        This section enters and exits smoothly using AnimatePresence.
      */}
      <AnimatePresence>
        {detailOpen && selected && (
          <motion.section id="planner" className="planner shell" initial={{opacity:0,y:40}} animate={{opacity:1,y:0}} exit={{opacity:0,y:20}}>
            {selected.recognitionMode ? (
              <>
                {/*
                  RECOGNIZED DESTINATION TRIP CANVAS

                  The recognized landmark version of the Trip Canvas uses the
                  location information returned from Neon instead of filling
                  the page with fake travel recommendations.

                  Flight, hotel, restaurant and nearby landmark cards remain
                  visible so the user can see what Trekmark will add during
                  the next integration phase.
                */}
                <div className="planner-head planner-head--recognized">
                  <div>
                    <div className="eyebrow">Trekmark trip canvas</div>
                    <h2>Build a trip around {selected.name}.</h2>
                    <p>
                      Start with what Trekmark already knows about the landmark,
                      then add live travel planning as those services are connected.
                    </p>
                  </div>
                  <button className="icon-btn" onClick={()=>setDetailOpen(false)}><X/></button>
                </div>

                <div
                  className="recognized-trip-hero"
                  style={{
                    backgroundImage:
                      `linear-gradient(90deg, rgba(5,9,14,.88), rgba(5,9,14,.32)), url(${selected.hero})`
                  }}
                >
                  <div className="recognized-trip-hero__copy">
                    <span>Recognized destination</span>
                    <h3>{selected.name}</h3>
                    <p><MapPin size={15}/> {selected.country}</p>
                    <div className="recognized-trip-confidence">
                      {selected.confidence}% match confidence
                    </div>
                  </div>
                </div>

                {/*
                  The Trip Canvas keeps the database details user-facing.
                  City, state and country are shown when available, while
                  internal identifiers and coordinates stay out of the UI.
                */}
                <div className="destination-profile">
                  <div className="destination-profile__head">
                    <div>
                      <span>Destination profile</span>
                      <h3>What Trekmark knows so far</h3>
                    </div>

                    <div className="destination-profile__actions">
                      <button
                        className="profile-explore-button"
                        type="button"
                        onClick={() => {
                          const nextSection = document.querySelector(
                            '.landmark-gallery-section, .nearby-landmarks-section, .planning-next-head'
                          );

                          nextSection?.scrollIntoView({
                            behavior: 'smooth',
                            block: 'start'
                          });
                        }}
                      >
                        <span>Explore what&apos;s nearby</span>
                        <ChevronDown size={17}/>
                      </button>

                      <span className="profile-source">Landmark database</span>
                    </div>
                  </div>

                  <div className="destination-profile__grid destination-profile__grid--simple">
                    <div className="profile-field">
                      <span>Landmark</span>
                      <strong>{selected.name || 'Not available'}</strong>
                    </div>
                    <div className="profile-field">
                      <span>City</span>
                      <strong>{selected.city || 'Not available'}</strong>
                    </div>
                    <div className="profile-field">
                      <span>State / region</span>
                      <strong>{selected.state || 'Not available'}</strong>
                    </div>
                    <div className="profile-field">
                      <span>Country</span>
                      <strong>{selected.countryName || 'Not available'}</strong>
                    </div>
                  </div>
                </div>

                {selected.galleryImages?.filter((image) => image && image !== selected.hero).length > 0 && (
                  <div className="landmark-gallery-section">
                    <div className="trip-section-heading">
                      <div>
                        <span>More of this landmark</span>
                        <h3>See {selected.name} from another angle.</h3>
                      </div>
                      <p>
                        Additional images associated with this landmark in Trekmark's database.
                      </p>
                    </div>

                    <div className="landmark-gallery-grid">
                      {selected.galleryImages
                        .filter((image) => image && image !== selected.hero)
                        .slice(0, 3)
                        .map((image, index) => (
                          <div
                            className="landmark-gallery-image"
                            key={`${image}-${index}`}
                            style={{
                              backgroundImage:
                                `linear-gradient(180deg, rgba(5,9,14,.02), rgba(5,9,14,.3)), url(${image})`
                            }}
                          />
                        ))}
                    </div>
                  </div>
                )}

                {selected.nearbyLandmarks?.length > 0 && (
                  <div className="nearby-landmarks-section">
                    <div className="trip-section-heading">
                      <div>
                        <span>Explore nearby</span>
                        <h3>Landmarks within reach.</h3>
                      </div>
                      <p>
                        Nearby places are ranked by distance from {selected.name}.
                      </p>
                    </div>

                    <div className="nearby-landmarks-grid">
                      {selected.nearbyLandmarks.slice(0, 3).map((landmark) => (
                        <div className="nearby-landmark-card" key={landmark.id}>
                          <div
                            className="nearby-landmark-card__image"
                            style={{
                              backgroundImage:
                                `linear-gradient(180deg, rgba(5,9,14,.02), rgba(5,9,14,.58)), url(${landmark.image || selected.hero})`
                            }}
                          >
                            <span>{Math.round(landmark.distance_km)} km away</span>
                          </div>

                          <div className="nearby-landmark-card__copy">
                            <strong>{landmark.name}</strong>
                            <span>
                              {[landmark.city, landmark.state, landmark.country]
                                .filter(Boolean)
                                .join(', ')}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="planning-next-head">
                  <div>
                    <span>Next planning layer</span>
                    <h3>Turn the landmark into a trip.</h3>
                  </div>
                  <p>
                    These cards are already part of the Trekmark experience.
                    Live travel providers will populate them during the next phase.
                  </p>
                </div>

                <div className="trip-grid trip-grid--future trip-grid--future-three">
                  <div className="trip-card trip-card--future">
                    <div
                      className="future-card-image future-card-image--flight"
                      style={{ backgroundImage: `linear-gradient(180deg, rgba(5,9,14,.06), rgba(5,9,14,.7)), url(${selected.hero})` }}
                    />
                    <div className="future-card-copy">
                      <Plane/>
                      <span>Flight</span>
                      <strong>Routes to {selected.city || selected.countryName}</strong>
                      <small>Live fares and departure options will be added in the next integration phase.</small>
                    </div>
                  </div>

                  <div className="trip-card trip-card--future">
                    <div
                      className="future-card-image future-card-image--stay"
                      style={{ backgroundImage: `linear-gradient(180deg, rgba(5,9,14,.06), rgba(5,9,14,.7)), url(${selected.hero})` }}
                    />
                    <div className="future-card-copy">
                      <Hotel/>
                      <span>Stay</span>
                      <strong>Hotels near {selected.name}</strong>
                      <small>Future results will use the recognized landmark as the center of the stay search.</small>
                    </div>
                  </div>

                  <div className="trip-card trip-card--future">
                    <div
                      className="future-card-image future-card-image--eat"
                      style={{ backgroundImage: `linear-gradient(180deg, rgba(5,9,14,.06), rgba(5,9,14,.7)), url(${selected.hero})` }}
                    />
                    <div className="future-card-copy">
                      <UtensilsCrossed/>
                      <span>Eat</span>
                      <strong>Dining around {selected.city || selected.name}</strong>
                      <small>Nearby restaurants, ratings and pricing will populate this card later.</small>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <>
                <div className="planner-head">
                  <div><div className="eyebrow">Trekmark trip canvas</div><h2>{selected.name}, in one glance.</h2><p>{selected.summary}</p></div>
                  <button className="icon-btn" onClick={()=>setDetailOpen(false)}><X/></button>
                </div>

                {
}
                {/* Travel recommendations based on images. The hope is that
                    the user can imagine themselves in the photo at the destination. */}
                <div className="planner-media">
                  {/* This section is DRY because of the use of .map(). Same
                      structure, different content. If we ever add another image card,
                      we can mostly just update the array above rather than manually
                      typing out another section of JSX. */}
                  {plannerVisuals.map((visual, index) => (
                    <div
                      key={`${visual.kind}-${index}`}
                      className={visual.className}
                      style={{ backgroundImage: `linear-gradient(180deg, rgba(6,10,16,.08), rgba(6,10,16,.78)), url(${visual.image})` }}
                    >
                      <div className="planner-visual__copy">
                        <span>{visual.kind}</span>
                        <strong>{visual.title}</strong>
                      </div>
                    </div>
                  ))}
                </div>

                {
}
                {/* Cards that give a short summary of the trip planning.
                    Prices shown here are demo/placeholder until travel APIs are connected. */}
                <div className="trip-grid">
                  <div className="trip-card">
                    <Plane/>
                    <span>Flight snapshot</span>
                    <strong>{selected.flight}</strong>
                    <small>Sample fare · economy</small>
                  </div>
                  <div className="trip-card">
                    <Hotel/>
                    <span>Stay</span>
                    <strong>{selected.hotel}</strong>
                    <small>{selected.stayPrice || '$—'} · central location</small>
                  </div>
                  <div className="trip-card">
                    <UtensilsCrossed/>
                    <span>Eat</span>
                    <strong>{selected.restaurant}</strong>
                    <small>{selected.eatPrice || '$—'} · popular nearby choice</small>
                  </div>
                  <div className="trip-card">
                    <Star/>
                    <span>Do</span>
                    <strong>{selected.attraction}</strong>
                    <small>{selected.doPrice || '$—'} · must-see experience</small>
                  </div>
                </div>
                {
}
                {/* A sample 3-day trip plan for the selected destination.
                    Also demo data for the prototype. */}
                <div className="itinerary">
                  <div className="itinerary-title"><div><span>Suggested 3-day rhythm</span><h3>Enough structure. Still feels like a vacation.</h3></div><span className="ai-pill"><Sparkles size={14}/> AI assembled</span></div>
                  {[['Day 1','Arrive + orient','Check in, walk the central district, then keep the first evening flexible.'],['Day 2','Signature day',`Start with ${selected.attraction}, leave room for a long lunch, then explore one nearby neighborhood.`],['Day 3','Local texture','Slow morning, one hidden-gem stop, then an easy route back toward departure.']].map(([d,t,b])=><div className="day" key={d}><span>{d}</span><div><strong>{t}</strong><p>{b}</p></div></div>)}
                </div>
              </>
            )}
          </motion.section>
        )}
      </AnimatePresence>

      {


}
      {/*
        COMMUNITY LANDMARK SUBMISSION

        Users can suggest a landmark that is not already represented in Trekmark.
        City, state, latitude and longitude are optional because those values are
        not available for every landmark.
      */}
      <section
        className={`submission-section shell ${
          submissionStatus === 'success'
            ? 'submission-section--success'
            : submissionStatus === 'error'
              ? 'submission-section--error'
              : ''
        }`}
        id="submit-landmark"
      >
        {submissionStatus === 'success' || submissionStatus === 'error' ? (
          <motion.div
            className="submission-result"
            initial={{ opacity: 0, scale: .97, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{ duration: .38, ease: 'easeOut' }}
          >
            <motion.div
              className={`submission-result__icon ${
                submissionStatus === 'success'
                  ? 'submission-result__icon--success'
                  : 'submission-result__icon--error'
              }`}
              initial={{ scale: .5, rotate: -12 }}
              animate={{ scale: 1, rotate: 0 }}
              transition={{ delay: .12, type: 'spring', stiffness: 260, damping: 18 }}
            >
              {submissionStatus === 'success' ? (
                <Sparkles size={30}/>
              ) : (
                <X size={30}/>
              )}
            </motion.div>

            <div className="submission-result__copy">
              <div className="eyebrow">
                {submissionStatus === 'success'
                  ? 'Submission received'
                  : 'Something went wrong'}
              </div>

              <h2>
                {submissionStatus === 'success'
                  ? 'Thanks for helping Trekmark grow.'
                  : 'We could not submit that landmark.'}
              </h2>

              <p>
                {submissionStatus === 'success'
                  ? 'Your landmark has been saved and can now be reviewed before it is added to Trekmark.'
                  : 'Your information was not confirmed as saved. You can return to the form and try again.'}
              </p>
            </div>

            <button
              className="primary submission-result__button"
              type="button"
              onClick={resetSubmission}
            >
              {submissionStatus === 'success'
                ? 'Add another landmark'
                : 'Try again'}
              <ArrowRight size={16}/>
            </button>
          </motion.div>
        ) : (
          <>
            <div className="submission-copy">
              <div className="eyebrow">Help Trekmark grow</div>
              <h2>Know a landmark we should add?</h2>
              <p>
                Send us the landmark and an image source. Your submission can be
                reviewed before it is added to Trekmark's landmark collection.
              </p>

              {submissionImageUrl ? (
                <div
                  className="submission-preview"
                  style={{ backgroundImage: `linear-gradient(180deg, rgba(5,9,14,.04), rgba(5,9,14,.58)), url(${submissionImageUrl})` }}
                >
                  <span>Image preview</span>
                </div>
              ) : (
                <div className="submission-preview submission-preview--empty">
                  <Camera size={26}/>
                  <span>Your image preview will appear here</span>
                </div>
              )}
            </div>

            <form className="submission-form" onSubmit={submitLandmark}>
              <div className="submission-field submission-field--wide">
                <label htmlFor="submission-name">Landmark name</label>
                <input
                  id="submission-name"
                  name="name"
                  type="text"
                  placeholder="Example: Stirling Castle"
                  required
                />
              </div>

              <div className="submission-field submission-field--wide">
                <label htmlFor="submission-image-url">Image URL</label>
                <input
                  id="submission-image-url"
                  name="image_url"
                  type="url"
                  placeholder="https://example.com/landmark.jpg"
                  value={submissionImageUrl}
                  onChange={(e) => setSubmissionImageUrl(e.target.value)}
                  required
                />
              </div>

              <div className="submission-field">
                <label htmlFor="submission-city">City <span>Optional</span></label>
                <input
                  id="submission-city"
                  name="city"
                  type="text"
                  placeholder="Stirling"
                />
              </div>

              <div className="submission-field">
                <label htmlFor="submission-state">State / region <span>Optional</span></label>
                <input
                  id="submission-state"
                  name="state"
                  type="text"
                  placeholder="Scotland"
                />
              </div>

              <div className="submission-field submission-field--wide">
                <label htmlFor="submission-country">Country</label>
                <input
                  id="submission-country"
                  name="country"
                  type="text"
                  placeholder="United Kingdom"
                  required
                />
              </div>

              <div className="submission-field">
                <label htmlFor="submission-latitude">Latitude <span>Optional</span></label>
                <input
                  id="submission-latitude"
                  name="lat"
                  type="number"
                  step="any"
                  placeholder="56.1239"
                />
              </div>

              <div className="submission-field">
                <label htmlFor="submission-longitude">Longitude <span>Optional</span></label>
                <input
                  id="submission-longitude"
                  name="lon"
                  type="number"
                  step="any"
                  placeholder="-3.9478"
                />
              </div>

              <div className="submission-form__footer">
                <div className="submission-status">
                  {submissionStatus === 'submitting' && 'Saving your landmark submission…'}
                </div>

                <button
                  className="primary"
                  type="submit"
                  disabled={submissionStatus === 'submitting'}
                >
                  {submissionStatus === 'submitting' ? 'Submitting…' : 'Submit landmark'}
                  <ArrowRight size={16}/>
                </button>
              </div>
            </form>
          </>
        )}
      </section>

      {


}
      {/*
        FINAL CALL TO ACTION

        Performs the upload action again for users that scroll to the bottom of the page.
      */}
      <section className="final-cta shell">
        <div>
          <div className="eyebrow">See somewhere worth knowing?</div>
          <h2>Show Trekmark.</h2>
          <p>Upload any place or landmark that caught your attention. Trekmark will help identify it and turn that discovery into somewhere you can actually go.</p>
        </div>
        <button className="primary" onClick={() => fileRef.current?.click()}>
          <Camera size={18}/> Identify a place
        </button>
      </section>

      {}
      {/* Footer briefly describing the four main products offered by Trekmark. */}
      <footer className="shell"><span>Trekmark</span><span>Landmark recognition · confidence · regional exploration · trip planning</span></footer>

      <AnimatePresence>
        {analyzing && <motion.div className="analysis-overlay" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}}>
          <div className="scan-card">
            {uploadPreview && <img src={uploadPreview} alt="Uploaded preview"/>}
            <div className="scan-line"/><div className="scan-copy"><span><Sparkles size={15}/> Trekmark Vision</span><h3>Reading the scene…</h3><p>Matching visual landmarks and regional context.</p></div>
          </div>
        </motion.div>}
      </AnimatePresence>
      </main>
    </>
  );
}


// Take the <div id="root"></div> from index.html and put the entire
// Trekmark React app into it. From this point on React will handle the page.
// index.html only provides an empty root element. The App() is what will
// actually display Trekmark in the browser.
createRoot(document.getElementById('root')).render(<App />);
