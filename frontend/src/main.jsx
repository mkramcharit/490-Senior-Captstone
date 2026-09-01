


/*
TREKMARK FRONT END - main.jsx

This file holds the bulk of all React functionality within the current
Trekmark prototype.

The purpose of this prototype is:

1. Allow the user to find a destination by either clicking on a location
   on the globe or by uploading an image.
2. Show a preview card of the chosen destination.
3. Enable the user to enter a more detailed “Trip Canvas” with sample
   data for flight, hotel, food, attractions, pricing, and itinerary.
4. Keep the interface very visual to provide a travel product experience
   instead of a technical capstone/research project.

*/
import React, { useEffect, useMemo, useRef, useState } from 'react';

// React 18+ uses createRoot to mount the app to index.html
import { createRoot } from 'react-dom/client';


// Framer Motion is used for smooth transitions when sliding and fading in/out.
// AnimatePresence is useful for removing elements as CSS has limited support
// for animating elements after removal by React.
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


// All styling, responsiveness, globe styling, background animation,
// fixed navigation and Trip Canvas layout is defined here.
import './styles.css';


/*
PRESET GLOBE DESTINATIONS

These are the five destinations currently on the globe.

Each object has the following properties:

- id: React internal id
- name/country: rendered in UI
- lat/lng: actual lat/lng for map pin
- kicker: short promotional copy
- confidence: fake confidence level for recognition (only for prototype)
- hero / experienceImage / stayImage / eatImage: individual images so the
  Trip Canvas doesn't reuse the same image
- hotel / restaurant / attraction: sample travel options
- stayPrice / eatPrice / doPrice / flight: sample prices

Once the backend exists, a large amount of this data will come from the API
instead of being hardcoded here.

Having all the preset destinations in one array makes the rest of
the page a lot easier to work with. Rather than hard coding Orlando, Tokyo, Paris,
etc. in five different places, React can loop over the same data and use it in multiple
places. This is much cleaner and should make integration to the backend even less
painful as we can replace mock data with API data.
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

The large full width image carousel found lower on the page.

There are five globe presets but some gallery items have their own custom
"trip" object. This enables a user to click "Plan this trip" on a gallery item and use
the same Trip Canvas as used in the globe.

For Tokyo and the Amazon we reuse an existing destination object via
destinations.find(...). No duplicate data is created.

The gallery is structured similarly to the globe using data.
Some items have their own trip object, while others reuse an existing
destination using .find(). Again, reusing an object here avoids copying
duplicate data across the entire file. Things would quickly become messy
if we copy/paste data everywhere.
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

These are the small glowing particles in the background.

The position, size, delay and duration of each particle is randomized once.
useMemo is used here to avoid the particles jumping to new random
positions every time the page is re-rendered by React.

This is mostly visual polish, but it does go a long way towards making the
page feel dynamic rather than entirely static in the mockup. We keep the
effect fairly lightweight since there's no benefit in cooking the GPU
for small background dots.
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

The current implementation of the globe is performance optimized.

Rather than warping a high-resolution texture repeatedly in JavaScript,
we instead shift copies of a real world map texture within a circular
container horizontally. The location dots are drawn INSIDE the same
map texture. Since both the map and the location dots are moving together,
the dots stay in their correct geographic positions.

This gives us:

- A rotating earth-like globe
- Accurate placement of continents
- Markers that adhere to the map
- Much lower latency compared to our canvas-warp implementations

Props:

- selected: the currently selected location
- onSelect: called when a marker is clicked

The globe appears a bit complex, but the actual concept is actually quite
simple. A map with its markers all flow within a circular view. This eliminates
the issue of marker drift and provides the appearance of a rotating Earth
without the overhead of a much heavier full 3D globe library.
*/
function CanvasGlobe({ selected, onSelect }) {
  
  // Reference to the visible circular viewing "window" that crops the map.
  const viewportRef = useRef(null);

  
  
  // We create several copies of the world map in order to be able to loop the map
  // infinitely, without leaving whitespace on the left or right sides.
  const worldRefs = useRef([]);

  
  
  // Current longitude/rotation value. Instead of state, we use refs because this
  // gets updated every animation frame and SHOULD NOT cause React re-renders.
  const rotationRef = useRef(-28);

  
  
  // The longitude we smoothly rotate toward if a destination is clicked.
  const targetRotationRef = useRef(null);

  
  
  // Pauses automatic rotation for a short time when a destination is focused. This
  // gives the user time to look at their focused destination.
  const pauseUntilRef = useRef(0);

  
  // Stores requestAnimationFrame to be cancelled later during cleanup.
  const rafRef = useRef(null);

  
  
  // Used for calculating the time that has elapsed since the last frame. This
  // enables smooth animation across 60 Hz, 120 Hz and 144 Hz displays.
  const lastTimeRef = useRef(performance.now());

  
  
  // To select a new location, have the globe animate to rotate to the
  // longitude of the new location, then stop the automatic rotation for
  // 2.6 seconds.
  useEffect(() => {
    if (!selected) return;
    targetRotationRef.current = selected.lng;
    pauseUntilRef.current = performance.now() + 2600;
  }, [selected]);

  
  
  
  // Animation loop for the globe.
  // Runs once when the globe is mounted and removes itself when the
  // component is removed.
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

      // 560 is a fallback value if the browser has not completed measuring
      // the globe yet. This prevents the first animation frame from performing
      // strange calculations while the layout is still settling.
      const viewportWidth = viewport.clientWidth || 560;
      const worldWidth = viewportWidth * 2;

      
      // Center the currently/selected longitude in the circular view.
      const normalizedRotation =
        ((rotationRef.current + 180) % 360 + 360) % 360;

      const centerOnTrack =
        (normalizedRotation / 360) * worldWidth;

      const translateX =
        viewportWidth / 2 - centerOnTrack;

      
      
      
      // The markers are INSIDE each world.
      // The world and markers are translated together as one object,
      // meaning the labels will always be in the correct geographic
      // location.
      //
      // Each copy of a world receives the same translation value. This is what
      // allows the repeating texture to appear as a single globe rather than
      // three separate worlds moving independently.
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

  
  
  // A function that creates one instance of the world texture and all
  // destination markers. Three instances are created for horizontal looping.
  const renderWorldCopy = (copyKey, leftPercent, refIndex) => (
    <div
      key={copyKey}
      ref={(el) => { worldRefs.current[refIndex] = el; }}
      className="locked-world"
      style={{ left: leftPercent }}
    >
      <div className="locked-world__texture" />

      {destinations.map((d) => {
        
        
        
        
        
        
        
        
        // Takes latitude and longitude and converts them to percentages
        // on an equirectangular world map.
        //
        // Longitude:
        // -180 degrees = far left, +180 degrees = far right.
        //
        // Latitude:
        // +90 degrees = top (North Pole), -90 degrees = bottom.
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

App() creates the main user visible elements and assembles all
sections of the page. Most of the app is currently a single page
application. As the user moves through the app, links cause changes
in React state instead of transitioning to entirely new HTML pages.

App() is essentially in charge of managing the page state. It tracks data such
as which destination is selected, whether the Trip Canvas is visible, which
gallery slide is currently displayed and whether the fake AI image scanning
screen is currently visible.
*/
function App() {
  
  
  // Hidden input used for file input. Utilised by various buttons in the app to
  // let the user select a file using the user's default file picker.
  const fileRef = useRef();

  
  // Currently selected destination. If null then no destination has been selected.
  const [selected, setSelected] = useState(null);

  
  // Boolean used to show or hide the detailed Trekmark Trip Canvas
  const [detailOpen, setDetailOpen] = useState(false);

  
  // Temporary URL for the uploaded image stored locally
  const [uploadPreview, setUploadPreview] = useState(null);

  
  // Boolean used to show or hide the fake AI image scanning screen
  const [analyzing, setAnalyzing] = useState(false);

  
  // Current image in large rotating image display
  const [galleryIndex, setGalleryIndex] = useState(0);

  
  
  
  // Advances cinematic destination gallery every 5.2 sec.
  // Will cancel interval when component is destroyed via cleanup function.
  useEffect(() => {
    const t = setInterval(
      () => setGalleryIndex(i => (i + 1) % gallery.length),
      5200
    );
    return () => clearInterval(t);
  }, []);

  
  
  
  // Called when one of the globe markers are clicked. Selects the
  // destination, closes any existing planner and scrolls down to the
  // destination preview card.
  //
  // We use the short timeout to give React time to render the new
  // destination card before we scroll to it. Otherwise, we can sometimes
  // scroll too early and end up in an awkward position. This is lowkey annoying.
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

  
  
  // Unselects the selected destination, hides the destination preview
  // card and returns the user to the state of discovering the globe.
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

  
  
  // Opens the Trip Canvas for the image in the currently viewed cinematic
  // gallery. Now the gallery serves a purpose and is not purely decorative.
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
  // Use individual image inputs rather than repeating the same
  // image since it would be uninteresting to a travel planner.
  //
  // Creating this array up front results in a lot cleaner JSX below. Rather than
  // manually creating four nearly-identical image components, we define the data
  // once and have .map() handle the repetition for us.
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

  
  
  
  
  
  
  
  
  
  
  
  // Prototype image upload flow.
  //
  // Currently:
  //
  // 1. Read selected image file,
  // 2. Generate URL for local preview of image,
  // 3. Show scanning screen,
  // 4. Pause for 1.8 seconds,
  // 5. Simulate AI recognizing Paris,
  // 6. Show Trip Canvas
  //
  // Steps 4-5 in the app will use the backend /predict API.
  //
  // Optional chaining on files?.[0] will help handle the case when the user opens
  // the file picker then cancels. While this is a small check, it will prevent an
  // error from occurring when encountering completely normal user input.
  const onUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadPreview(URL.createObjectURL(file));
    setAnalyzing(true);
    setTimeout(() => {
      setAnalyzing(false);
      setSelected(destinations[2]);
      setDetailOpen(true);
      setTimeout(() => document.querySelector('#planner')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 120);
    }, 1800);
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
              <div className="selected-copy">
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
          </motion.section>
        )}
      </AnimatePresence>

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
