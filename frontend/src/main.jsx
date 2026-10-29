


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
import HotelResults from './HotelResults.jsx';
import RestaurantResults from './RestaurantResults.jsx';
import AirportResults from './AirportResults.jsx';
import { destinationFromResponse, presetIdFor } from './destinationData.js';
import { AccountProvider, AccountNav, SaveItinerary, ItineraryPlan, apiErrorMessage } from './AccountPanel.jsx';
import AdminPage from './AdminPage.jsx';


// Recognized landmark photos come exclusively from the Neon-backed prediction
// response. If the first database image fails, try another database image.
// Wikimedia photos belong only to HotelResults and are never read here.
function NeonLandmarkImage({ destination }) {
  const sources = useMemo(() => [...new Set([
    destination.hero, ...(destination.galleryImages || []),
  ].filter(image => typeof image === 'string' && image.trim()))],
    [destination.hero, destination.galleryImages]);
  const [index, setIndex] = useState(0);
  useEffect(() => setIndex(0), [sources]);
  if (!sources[index]) return null;
  return <img className="recognized-trip-hero__image" src={sources[index]}
    alt={destination.name} onError={() => setIndex(current => current + 1)}/>;
}


// Keep anchor targets below the fixed header, including at mobile widths.
function scrollToTripSection(id) {
  const target = document.getElementById(id);
  if (!target) return;
  if (id === 'trip-itinerary') {
    const editor = target.querySelector('details');
    if (editor) editor.open = true;
  }
  target.focus({ preventScroll: true });
  target.scrollIntoView({
    behavior: window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth',
    block: 'start',
  });
}

function TripNavigationStyles() {
  return <style>{`
    :root { --trekmark-header-height: 72px; }
    #planner, .trip-anchor { scroll-margin-top: calc(var(--trekmark-header-height) + 24px); }
    .trip-anchor:focus, #planner:focus { outline: none; }
    .trip-jump { display:flex; align-items:center; flex-wrap:wrap; gap:10px; padding:18px 20px; margin:0 0 24px; border:1px solid #ffffff26; border-radius:20px; background:linear-gradient(120deg,#23394de6,#222337e6); }
    .trip-jump__intro { flex:1 1 210px; }
    .trip-jump__intro strong { display:block; color:#f3f8ff; font-size:16px; }
    .trip-jump__intro span { display:block; margin-top:5px; color:#b9c8da; font-size:13px; line-height:1.5; }
    .trip-jump button, .trip-next { display:inline-flex; align-items:center; justify-content:center; gap:8px; padding:12px 16px; border:1px solid #97c9ff45; border-radius:999px; background:#ffffff09; color:#e8f4ff; font:inherit; font-size:14px; cursor:pointer; transition:background .2s; }
    .trip-jump button:hover, .trip-next:hover { background:#8bc8ff25; }
    .trip-jump button:focus-visible, .trip-next:focus-visible { outline:2px solid #8bc8ff; outline-offset:4px; }
    .destination-profile .destination-profile__actions { flex-direction:row; flex-wrap:wrap; align-items:center; gap:12px; }
    .trip-save-inline { min-width:0; max-width:100%; }
    #planner .trip-save-inline .save-itinerary { display:flex; padding:0; margin:0; border:0; border-radius:0; background:none; box-shadow:none; gap:0; }
    #planner .trip-save-inline .save-itinerary > div,
    #planner .trip-save-inline .save-itinerary > small { display:none; }
    #planner .trip-save-inline .save-itinerary > button { max-width:100%; min-height:44px; white-space:normal; }
    .trip-stop { margin-top:28px; }
    .trip-next { margin:18px 0 4px; }
    .trip-finish { margin-top:32px; padding-top:24px; border-top:1px solid #ffffff26; }
    .trip-finish h3 { margin:0 0 8px; font-size:24px; letter-spacing:-.02em; }
    .trip-finish > p { margin:0 0 18px; color:#b9c8da; line-height:1.6; }
    @media(max-width:640px) {
      .trip-jump { padding:16px; gap:8px; }
      .trip-jump__intro { flex-basis:100%; margin-bottom:6px; }
      .trip-jump button { flex:1 1 calc(50% - 8px); font-size:13px; padding:12px 10px; }
      #planner .save-itinerary { flex-wrap:wrap; gap:14px; }
      #planner .save-itinerary > div { flex:1 1 100%; }
    }
    @media(prefers-reduced-motion:reduce) { html { scroll-behavior:auto; } }
  `}</style>;
}

// In dev the FastAPI server is running independently of the Vite frontend.
// All landmark recognition requests are sent to this server.
// Keep local API cookies on the same host as the Vite page (localhost or 127.0.0.1).
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || `http://${window.location.hostname}:8000`;


/*
PRESET GLOBE DESTINATIONS

There are currently 5 destinations on the globe.

Each of these has the following properties:

- id: React internal id
- name/country: displayed in UI
- lat/lng: the real lat/lng to use for a map pin
- kicker: short promotional copy
- confidence: provided only by recognition; featured selections have none
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
    kicker: 'Theme parks · sunshine · easy escapes',
    hero: 'https://images.unsplash.com/photo-1533107862482-0e6974b06ec4?auto=format&fit=crop&w=1600&q=90',
    summary: 'An energy-packed escape built around immersive lands, headline rides, resort nights and easy weekend momentum.',
  },
  {
    id: 'tokyo', name: 'Tokyo', country: 'Japan', lat: 35.6762, lng: 139.6503,
    kicker: 'Neon nights · ramen · quiet temples',
    hero: 'https://images.unsplash.com/photo-1540959733332-eab4deabeeaf?auto=format&fit=crop&w=1600&q=90',
    summary: 'A city that can feel futuristic, traditional, electric and calm in the same afternoon.',
  },
  {
    id: 'paris', name: 'Paris', country: 'France', lat: 48.8566, lng: 2.3522,
    kicker: 'Art · cafés · iconic streets',
    hero: 'https://images.unsplash.com/photo-1502602898657-3e91760cbb34?auto=format&fit=crop&w=1600&q=90',
    summary: 'Landmarks you already know, neighborhoods you do not, and a city built for wandering slowly.',
  },
  {
    id: 'amazon', name: 'Amazon gateway · Manaus', country: 'Brazil', lat: -3.13, lng: -60.02,
    kicker: 'Wildlife · rivers · immersive nature',
    hero: 'https://images.unsplash.com/photo-1516026672322-bc52d61a55d5?auto=format&fit=crop&w=1600&q=90',
    summary: 'A deeper kind of trip—river routes, layered green horizons and wildlife beyond the city grid.',
  },
  {
    id: 'rio', name: 'Rio de Janeiro', country: 'Brazil', lat: -22.9068, lng: -43.1729,
    kicker: 'Beaches · mountains · nightlife',
    hero: 'https://images.unsplash.com/photo-1483729558449-99ef09a8c325?auto=format&fit=crop&w=1600&q=90',
    summary: 'Oceanfront energy, dramatic peaks and a city that feels cinematic from almost every angle.',
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
      id: 'new-york', lat:40.7128, lng:-74.006, name: 'New York City', country: 'New York, USA',
      kicker: 'Skyline · neighborhoods · late nights',
      hero: 'https://images.unsplash.com/photo-1485871981521-5b1fd3805eee?auto=format&fit=crop&w=1800&q=90',
      summary: 'Iconic skyline views, neighborhood energy and more to do than a single weekend can hold.',
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
      id: 'great-wall', lat:40.4319, lng:116.5704, name: 'The Great Wall', country: 'Beijing, China',
      kicker: 'History · mountain views · day trips',
      hero: 'https://images.unsplash.com/photo-1508804185872-d7badad00f7d?auto=format&fit=crop&w=1800&q=90',
      summary: 'A landmark-scale trip combining Beijing culture with one of the world’s most recognizable landscapes.',
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
      id: 'amalfi', lat:40.634, lng:14.6027, name: 'Amalfi Coast', country: 'Campania, Italy',
      kicker: 'Cliffside towns · sea views · slow days',
      hero: 'https://images.unsplash.com/photo-1533104816931-20fa691ff6ca?auto=format&fit=crop&w=1800&q=90',
      summary: 'A coastal escape built around dramatic views, small towns, long lunches and time near the water.',
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
        
        
        
        
        
        
        
        
        // Converts a lat/lng location to a percentage on an equirectangular Earth.
        //
        // Longitude: -180 is left and +180 is right
        //
        // Latitude: +90 is top (North Pole) and -90 is bottom
        const x = ((d.lng + 180) / 360) * 100;
        const y = ((90 - d.lat) / 180) * 100;

        return (
          <button
            key={`${copyKey}-${d.id}`}
            className={`locked-marker ${selected?.id === d.id || selected?.presetId === d.id ? 'active' : ''}`}
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
  MAIN TREKMARK APP
  
  App() creates the elements of the currently visible page, and organizes them
  together into the page. Most of the app is currently a single page app. As a
  user progresses through the app, clicking on links will update the React
  state instead of transitioning to a new HTML page.
  
  App() is currently in charge of the page state. Currently tracks the currently
  selected destination, whether the detailed Trekmark Trip Canvas is visible, the
  currently uploaded image (temporary url), whether the AI image processing
  page is visible, and which image is currently displayed in the rotating image
  gallery.
*/
function App() {
  
  
  // Hidden input for image uploads. Used by multiple buttons across the app to let
  // the user select an image via the user's default file selection.
  const fileRef = useRef();

  
  // Currently selected destination. If this is null then no destination is selected
  // currently.
  const [selected, setSelected] = useState(null);
  const [featuredLoading, setFeaturedLoading] = useState(false);
  const [featuredError, setFeaturedError] = useState('');
  const featuredRequest = useRef(null);
  const selectionVersion = useRef(0);
  useEffect(() => () => featuredRequest.current?.abort(), []);

  
  // Boolean for showing/hiding detailed Trekmark Trip Canvas
  const [detailOpen, setDetailOpen] = useState(false);

  
  // Temporary url for the currently uploaded image
  const [uploadPreview, setUploadPreview] = useState(null);

  
  // Boolean for showing/hiding the AI image processing page
  const [analyzing, setAnalyzing] = useState(false);

  
  // Currently displayed image in rotating image gallery
  const [galleryIndex, setGalleryIndex] = useState(0);

  // Currently used form for submitting a Trekmark landmark.
  const [submissionStatus, setSubmissionStatus] = useState('');
  const [submissionImageUrl, setSubmissionImageUrl] = useState('');
  const [submissionImageFile, setSubmissionImageFile] = useState(null);
  const [submissionError, setSubmissionError] = useState('');
  useEffect(() => {
    if (!submissionImageFile) { setSubmissionImageUrl(''); return; }
    const url = URL.createObjectURL(submissionImageFile);
    setSubmissionImageUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [submissionImageFile]);

  // Use the fixed header size instead of the desktop height.
  useEffect(() => {
    const header = document.querySelector('.nav-fixed');
    const measure = () => document.documentElement.style.setProperty(
      '--trekmark-header-height', `${header?.getBoundingClientRect().height || 72}px`
    );
    measure();
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(measure) : null;
    if (header) observer?.observe(header);
    window.addEventListener('resize', measure);
    return () => { observer?.disconnect(); window.removeEventListener('resize', measure); };
  }, []);

  // Wait for the React planner to mount. When opacity only changes, the scroll
  // position is maintained while the component animates in. When notes are edited
  // this does not happen.
  useEffect(() => {
    if (!detailOpen || !selected) return;
    const timer = window.setTimeout(() => scrollToTripSection('planner'), 80);
    return () => window.clearTimeout(timer);
  }, [detailOpen, selected?.id]);

  const openSavedTrip = (destination) => {
    const presetId = presetIdFor(destination);
    if (presetId) { loadFeatured({ id: presetId }, true, destination); return; }
    selectionVersion.current += 1; featuredRequest.current?.abort();
    setFeaturedLoading(false); setFeaturedError('');
    setAnalyzing(false); setSelected(destination); setDetailOpen(true);

  };

  
  
  
  // Rotates the cinematic gallery of destinations every 5.2 seconds.
  // Clean up interval on component unmount.
  useEffect(() => {
    const t = setInterval(
      () => setGalleryIndex(i => (i + 1) % gallery.length),
      5200
    );
    return () => clearInterval(t);
  }, []);

  
  
  
  // Called when a destination from the globe is clicked on. Selects that destination,
  // hides any current planner, and scrolls down to the destination preview card.
  //
  // We use a timeout to allow React time to render the new destination preview card
  // before we scroll to it. Sometimes we scroll too early and end up in an awkward
  // position. This is lowkey annoying.
  const loadFeatured = async (destination, openPlanner = false, saved = null) => {
    const version = ++selectionVersion.current;
    featuredRequest.current?.abort();
    const controller = new AbortController(); featuredRequest.current = controller;
    setSelected(null); setDetailOpen(false); setAnalyzing(false); setFeaturedLoading(true); setFeaturedError('');
    setTimeout(() => document.querySelector('#discover')?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 100);
    try {
      const response = await fetch(`${API_BASE_URL}/api/featured/${encodeURIComponent(destination.id)}`, { signal: controller.signal });
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error(apiErrorMessage(data, 'This destination could not be loaded.'));
      const result = destinationFromResponse(data);
      if (controller.signal.aborted || selectionVersion.current !== version) return;
      setSelected(saved?.itinerary ? { ...result, itinerary: saved.itinerary } : result);
      setDetailOpen(openPlanner);

    } catch (error) {
      if (!controller.signal.aborted && selectionVersion.current === version) setFeaturedError(error instanceof TypeError ? 'Cannot reach the destination service. Check that the backend is running.' : error.message);
    } finally {
      if (selectionVersion.current === version) setFeaturedLoading(false);
    }
  };
  const focusDestination = destination => loadFeatured(destination);

  
  
  // Unselects the currently selected destination, hides the destination preview
  // card and returns the user to the globe.
  const clearDestination = () => {
    selectionVersion.current += 1; featuredRequest.current?.abort();
    setFeaturedLoading(false); setFeaturedError('');
    setSelected(null);
    setAnalyzing(false);
    setDetailOpen(false);
    window.setTimeout(() => {
      document.querySelector('#top')?.scrollIntoView({
        behavior: 'smooth',
        block: 'start'
      });
    }, 80);
  };

  
  
  // Opens the Trip Canvas for the currently displayed destination from the cinematic
  // gallery of destinations. This gives purpose to the gallery and is not purely
  // decorative.
  const planGalleryTrip = () => {
    const trip = gallery[galleryIndex]?.trip;
    if (trip) loadFeatured(trip, true);
  };

  
  
  
  // Image upload flow.
  //
  // The old app would always select Paris after a 1.8 second delay.
  // This app sends the selected image to the FastAPI /api/predict route.
  //
  // Current flow:
  //
  // 1. Read selected image file
  // 2. Create a preview for the scanning component
  // 3. Add image to FormData
  // 4. Send image to FastAPI
  // 5. FastAPI validates image and returns a landmark id and confidence
  // 6. FastAPI gets corresponding landmark info from Neon
  // 7. Convert returned data into same destination object format used throughout the
  //    app
  // 8. Display the returned destination on the page
  //
  // When not in demo mode on the backend, recognition uses DINOv2 + FAISS.
  // The image upload, FastAPI request, Neon lookup and React state update are all live.
  const onUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const version = ++selectionVersion.current;
    featuredRequest.current?.abort(); setFeaturedLoading(false); setFeaturedError('');

    const previewUrl = URL.createObjectURL(file);

    setUploadPreview(previewUrl);
    setAnalyzing(true);
    setDetailOpen(false);

    const formData = new FormData();
    formData.append('file', file);

    // Allow the scanning animation to stay visible until the user can see it.
    // The FastAPI request will still start immediately, but the response won't be
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
      if (selectionVersion.current !== version) return;

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(
          apiErrorMessage(errorData, 'Trekmark could not identify this image.')
        );
      }

      const data = await response.json();
      const backendDestination = destinationFromResponse(data);

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
      if (selectionVersion.current === version) setAnalyzing(false);

      // Allow the user to select the same image again after clearing the input.
      e.target.value = '';
    }
  };

  // User landmark submission flow.
  //
  // Users can submit a Trekmark landmark by providing a name, an image and a country.
  // City, state, latitude and longitude are optional because not all landmarks in
  // the Trekmark dataset include this information.
  //
  // The form is submitted as multipart FormData in order to support both direct
  // image uploads and the persistent image storage system.
  const submitLandmark = async (e) => {
    e.preventDefault();

    // Store the form before waiting for a response from the backend.
    // React's event currentTarget should not be trusted after an await.
    const formElement = e.currentTarget;
    const form = new FormData(formElement);

    if (submissionStatus === 'submitting') return;
    setSubmissionError('');
    if (!submissionImageFile || submissionImageFile.size > 10 * 1024 * 1024) {
      setSubmissionError('Choose a JPG, PNG or WebP image smaller than 10 MB.');
      return;
    }
    form.set('image', submissionImageFile);
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
          apiErrorMessage(errorData, 'Trekmark could not submit this landmark.')
        );
      }

      formElement.reset();
      setSubmissionImageFile(null);
      setSubmissionImageUrl('');
      setSubmissionStatus('success');
    } catch (error) {
      setSubmissionError(typeof error.message === 'string' ? error.message : 'The landmark could not be saved. Please try again.');
      // Preserve the form, file, and preview so that the user can correct a field.
      setSubmissionStatus('');
    }
  };

  // Returns the user submission form to a blank form so the user can either submit
  // another landmark or try again after a failed submission.
  const resetSubmission = () => {
    setSubmissionImageFile(null);
    setSubmissionError('');
    setSubmissionImageUrl('');
    setSubmissionStatus('');
  };

  return (
    <>
      {


}
      {/*
        FIXED NAVIGATION
        
        Now stays fixed during the scroll so that the logo, "How it works", login and upload
        are accessible throughout the app.
      */}
      <nav className="nav nav-fixed">
        <div className="nav-inner shell">
          <a className="brand" href="#top"><span className="brand-mark"><Compass size={16}/></span>Trekmark</a>
          <div className="nav-links">
            <a href="#how">How it works</a>
            <AccountNav onOpenTrip={openSavedTrip}/>
            <button className="upload-mini" onClick={() => fileRef.current?.click()}><Camera size={15}/> Upload photo</button>
          </div>
        </div>
      </nav>

      <main>
        <TripNavigationStyles/>
        {


}
        {/*
          TRAVEL BACKGROUND
          
          Decorative element. Combines flight paths, moving planes, sunsets and particles to
          create the feel of travel and discovery. aria-hidden prevents screen readers from
          treating this as content.
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
        
        Main copy and interactive world
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
        
        Is currently small and only visible if a destination is selected. If a destination
        is selected this is expanded into the large preview image with buttons "Build this
        trip" and "See something else".
      */}
      <section className="selected-strip shell" id="discover">
        {/*
          mode="wait" in Framer Motion removes the previous card before animating in the new
          card. This allows for a clean transition and ensures that both cards are not
          visible for a brief moment.
        */}
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
              <div className="selected-copy recognized-copy">
                <>
                    {/*
                      RECOGNIZED DESTINATION RESULT
                      
                      Selected images and suggested images all use the same Neon-backed destination
                      card. Only actual predictions have a confidence value.
                    */}
                    <div className="recognition-label">
                      <span className="recognition-dot" />
                      {selected.source === 'featured' ? 'Featured landmark' : 'Recognized landmark'}
                    </div>

                    <h2>{selected.name}</h2>

                    <div className="recognition-location">
                      <MapPin size={16}/> {selected.country}
                    </div>

                    <div className="recognition-facts">
                      <div>
                        {typeof selected.confidence === 'number' ? <><span title="Visual similarity to the closest reference image; not a verified probability of correctness.">Match confidence</span><strong>{selected.confidence}%</strong></> : <><span>Discover</span><strong>Featured pick</strong></>}
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

                        }}
                      >
                        Build this trip <ArrowRight size={16}/>
                      </button>
                      <button className="ghost compact selected-reset" onClick={clearDestination}>
                        {selected.source === 'featured' ? 'Explore another place' : 'Scan another photo'}
                      </button>
                    </div>
                  </>
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
              <span>{featuredLoading ? 'Loading your destination' : featuredError ? 'Destination unavailable' : 'Explore a featured destination'}</span>
              <strong role={featuredError ? 'alert' : 'status'}>{featuredError || (featuredLoading ? 'Finding the landmark, photos and location…' : 'Choose a point on the globe or a destination from the gallery.')}</strong>
            </motion.div>
          )}
        </AnimatePresence>
      </section>

      {


}
      {/*
        CINEMATIC GALLERY OF DESTINATIONS
        
        Travel images are automatically rotated. Users can also select a travel image and
        use that image to plan a trip.
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
        
        Short marketing copy for the Recognize -> Understand -> Go process. Not written
        as a research paper.
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
        
        Only appears when a user is planning a trip.
        Smoother on/off animations using AnimatePresence.
      */}
      <AnimatePresence>
        {detailOpen && selected && (
          <motion.section id="planner" tabIndex={-1} aria-label="Your trip planner" className="planner shell" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}}>
            <nav className="trip-jump" aria-label="Trip sections">
              <div className="trip-jump__intro"><strong>Your trip, all in one place</strong><span>Jump to your plan, airport, hotels or restaurants.</span></div>
              <button type="button" onClick={() => scrollToTripSection('trip-itinerary')}><Compass size={16}/> Itinerary</button>
              <button type="button" onClick={() => scrollToTripSection('trip-airport')}><Plane size={16}/> Airport</button>
              <button type="button" onClick={() => scrollToTripSection('trip-hotels')}><Hotel size={16}/> Hotels</button>
              <button type="button" onClick={() => scrollToTripSection('trip-restaurants')}><UtensilsCrossed size={16}/> Restaurants</button>
            </nav>
            <div id="trip-itinerary" className="trip-anchor" tabIndex={-1}>
              <ItineraryPlan destination={selected} onChange={itinerary => setSelected(current => ({ ...current, itinerary }))}/>
            </div>
            <>
                {/*
                  RECOGNIZED DESTINATION TRIP CANVAS
                  
                  Trip Canvas for a recognized destination uses the destination information
                  returned from Neon instead of filling the page with fake travel recommendations.
                  
                  Hotels are provided by Geoapify using the returned location.
                  Restaurants also use the returned location. Flights are a placeholder.
                */}
                <div className="planner-head planner-head--recognized">
                  <div>
                    <div className="eyebrow">Trekmark trip canvas</div>
                    <h2>Build a trip around {selected.name}.</h2>
                    <p>
                      {selected.presetId === 'amazon' ? 'Start your Amazon trip in Manaus, then explore nearby airports, places to stay and local restaurants.' : 'Make the plan yours, then explore nearby airports, places to stay and local restaurants.'}
                    </p>
                  </div>
                  <button className="icon-btn" onClick={()=>setDetailOpen(false)}><X/></button>
                </div>

                <div
                  className="recognized-trip-hero"
                >
                  <NeonLandmarkImage key={selected.id} destination={selected}/>
                  <div className="recognized-trip-hero__copy">
                    <span>{selected.source === 'featured' ? 'Featured destination' : 'Recognized destination'}</span>
                    <h3>{selected.name}</h3>
                    <p><MapPin size={15}/> {selected.country}</p>
                    {typeof selected.confidence === 'number' && <div className="recognized-trip-confidence">
                      {selected.confidence}% match confidence
                    </div>}
                  </div>
                </div>

                {/*
                  Trip Canvas keeps the database information user-facing.
                  City, state and country are provided if available. Internal IDs and coordinates
                  are not displayed.
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
                          scrollToTripSection('trip-hotels');
                        }}
                      >
                        <span>Explore what&apos;s nearby</span>
                        <ChevronDown size={17}/>
                      </button>

                      <div className="trip-save-inline">
                        <SaveItinerary destination={selected}/>
                      </div>
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
                            <span>{(landmark.distance_km / 1.609344).toFixed(1)} miles away</span>
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
                    Your nearest airport, local hotels and restaurants are ready to explore below.
                  </p>
                </div>

                <div className="trip-grid trip-grid--future hotels-future-grid" style={{gridTemplateColumns: '1fr'}}>
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


                </div>
              </>
            <section id="trip-airport" className="trip-anchor trip-stop" tabIndex={-1} aria-label="Closest airport">
              <AirportResults key={`airport-${selected.id}`} destination={selected} apiBaseUrl={API_BASE_URL}/>
              <button type="button" className="trip-next" onClick={() => scrollToTripSection('trip-hotels')}>Next: nearby hotels <ArrowRight size={16}/></button>
            </section>
            <section id="trip-hotels" className="trip-anchor trip-stop" tabIndex={-1} aria-label="Nearby hotels">
              <HotelResults key={selected.id} destination={selected} apiBaseUrl={API_BASE_URL}/>
              <button type="button" className="trip-next" onClick={() => scrollToTripSection('trip-restaurants')}>Next: local restaurants <ArrowRight size={16}/></button>
            </section>
            <section id="trip-restaurants" className="trip-anchor trip-stop" tabIndex={-1} aria-label="Local restaurants">
              <RestaurantResults key={`restaurants-${selected.id}`} destination={selected} apiBaseUrl={API_BASE_URL}/>
            </section>
            <section className="trip-finish" aria-label="Save your finished itinerary">
              <h3>A trip worth keeping.</h3>
              <p>Save your itinerary, or head back to your plan to make it yours.</p>
              <SaveItinerary destination={selected}/>
              <button type="button" className="trip-next" onClick={() => scrollToTripSection('trip-itinerary')}>Back to your itinerary <ChevronDown size={16} style={{transform:'rotate(180deg)'}}/></button>
            </section>
          </motion.section>
        )}
      </AnimatePresence>

      {


}
      {/*
        COMMUNITY LANDMARK SUBMISSION
        
        Users can suggest a landmark that is not in Trekmark.
        City, state, latitude and longitude are optional because not every landmark in
        the Trekmark dataset has these fields.
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
                  : submissionError || 'Your information was not confirmed as saved. You can return to the form and try again.'}
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
                Upload a photo and tell us where it is. Your submission will be
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
                <label htmlFor="submission-image">Landmark photo</label>
                <input id="submission-image" name="image" type="file" accept="image/jpeg,image/png,image/webp"
                  onChange={(event) => {
                    const file = event.target.files?.[0] || null;
                    setSubmissionError('');
                    if (file && file.size > 10 * 1024 * 1024) {
                      setSubmissionError('Choose an image smaller than 10 MB.'); event.target.value = ''; setSubmissionImageFile(null); return;
                    }
                    setSubmissionImageFile(file);
                  }} required/>
                <small>JPG, PNG or WebP · up to 10 MB</small>
                {submissionError && <p role="alert" className="account-error">{submissionError}</p>}
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
        
        Repeats the upload action for users that scroll to the bottom of the page.
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
      {/*
        Footer with a description of the 4 main products offered by Trekmark.
      */}
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


// Mount the entire Trekmark React app inside the <div id="root"></div> in index.html.
// From this point on React will control the page.
// index.html provides the root div. App() will be responsible for displaying
// Trekmark in the browser.
// Keep admin navigation separate from hotels and destination selection.
function RootApp() {
  const path = window.location.pathname;
  return <AccountProvider apiBaseUrl={API_BASE_URL}>{path === '/admin' || path.startsWith('/admin/') ? <AdminPage /> : <App />}</AccountProvider>;
}

createRoot(document.getElementById('root')).render(<RootApp />);
