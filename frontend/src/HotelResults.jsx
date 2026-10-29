/* HOTEL RESULTS

Use search results from the backend to show nearby hotels for the given destination.

For uploaded destinations, the initial hotel search can be run with Neon's lng/lat. For destinations
without an initial search, radius changes and retries use GET /api/hotels. The browser makes
requests to the backend but does not use the Geoapify API key.
*/
/* IMPORTS

React is used for the component. useState is used for local component state. useEffect is used for
making requests, cleanup, retry timers and state resets. Hotel, MapPin, Search and ExternalLink are
icons from lucide-react. Styles are imported from hotels.css.
*/
import React, { useEffect, useState } from 'react';
import { Hotel, MapPin, Search, ExternalLink } from 'lucide-react';
import './hotels.css';

/* HOTEL PHOTO COMPONENT

HotelPhoto is passed a hotel object and a callback for failure. failed tracks whether this photo has
failed to load. If hotel.image changes, reset failed to false. A React fragment is used to group the
photo and optional attribution. Loading an image with lazy loading and the hotel name as an alt text
allows the image to be loaded only when needed. The referrerPolicy is no-referrer to avoid the image
sending a Referer header when loaded. If the image fails to load, set failed to true and pass the
url to the parent. The parent will then remove all cards with that url from results. If no image is
available use Hotel icon with Photo unavailable text. The fallback may flash briefly before the card
is removed by the parent.
*/
function HotelPhoto({ hotel, onFailure }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [hotel.image]);
  return <><div className="hotel-result-card__photo">
    {hotel.image && !failed
      ? <img src={hotel.image} alt={hotel.name} loading="lazy" referrerPolicy="no-referrer" onError={() => { setFailed(true); onFailure(hotel.image); }}/>
      : <div className="hotel-result-card__photo-fallback"><Hotel size={34}/><span>Photo unavailable</span></div>}
    {/* PHOTO SOURCE LINK
    
    If an unfailed photo has an image_source field, and the image_source has an appropriate prefix of
    HTTP or HTTPS, show Photo source. When clicked, open the source in a new tab with noopener
    noreferrer. The regular expression checks the intended HTTP or HTTPS prefix. A prefix check is not
    an assurance that the photo is from a particular site.
    */}
    {hotel.image && !failed && hotel.image_source && /^https?:\/\//.test(hotel.image_source) && <a href={hotel.image_source} target="_blank" rel="noopener noreferrer">Photo source</a>}
  </div>
    {/* WIKIMEDIA COMMONS ATTRIBUTION
    
    For an unfailed photo with image_provider set to Wikimedia Commons, show image title or fallback
    title, author, and license. If image_license_url exists, render the license as a link, otherwise as
    text. Indicate that this photo is from Wikimedia Commons and has been cropped. React renders the
    provided title, author and license as text. This attribution does not independently verify the link
    URLs.
    */}
    {hotel.image && !failed && hotel.image_provider === 'Wikimedia Commons' && <div className="hotel-photo-credit">
      <a href={hotel.image_source} target="_blank" rel="noopener noreferrer">{hotel.image_title || 'Hotel photo'}</a>
      <span>Photo: {hotel.image_author}</span>
      {hotel.image_license_url
        ? <a href={hotel.image_license_url} target="_blank" rel="noopener noreferrer">{hotel.image_license}</a>
        : <span>{hotel.image_license}</span>}
      <span>Wikimedia Commons · cropped to fit</span>
    </div>}
  </>;
}

/* COMPONENT INPUTS

HotelResults is passed a destination and an apiBaseUrl from its parent. The destination provides a
name, a lat field for latitude, a lng field for longitude, and an optional hotelSearch result. There
should be a destination object present.
*/
/* SCOPE OF THIS COMPONENT

This component makes hotel requests, filters hotel results and displays hotel results and photo
attributions. Backend services provide hotel discovery, distance estimation, photo matching,
provider information and any server side caching. These comments explain the provided code. Markdown
corruption in the pasted JSX, URLs and regular expressions has been restored.
*/
export default function HotelResults({ destination, apiBaseUrl }) {
  /* LOCAL STATE
  
  radius starts at 5000 meters. search starts as destination.hotelSearch if present, otherwise null.
  loading starts as true if there is no truthy initial hotelSearch. filter is an empty string and is
  used to filter results by name locally. retry starts at zero and is used to track automatic retries.
  failedImages starts as an empty Set of image urls.
  */
  const [radius, setRadius] = useState(5000);
  const [search, setSearch] = useState(destination.hotelSearch || null);
  const [loading, setLoading] = useState(!destination.hotelSearch);
  const [filter, setFilter] = useState('');
  const [retry, setRetry] = useState(0);
  const [failedImages, setFailedImages] = useState(() => new Set());

  /* TRACK FAILED IMAGES
  
  On each change to search, reset failedImages. When an image fails to load, create a new Set with all
  of the previously failed URLs and add the currently failed url. This creates a new Set to allow
  React to track the change. If multiple hotels have the same failed URL, then all cards with that
  failed URL are omitted.
  */
  useEffect(() => setFailedImages(new Set()), [search]);
  const hideFailedImage = url => setFailedImages(previous => new Set([...previous, url]));

  /* RESET FOR A NEW LOCATION
  
  If either latitude or longitude changes, reset retry to zero and reset the hotel name filter. This
  does not run on changes to hotelSearch, radius, apiBaseUrl, or failed images. As a result, a radius
  change will not get a new retry count from this effect.
  */
  useEffect(() => {
    setRetry(0);
    setFilter('');
  }, [destination.lat, destination.lng]);

  /* AUTOMATIC RETRIES
  
  After loading is complete, if the status is error, timeout, or provider_error for a search and there
  have been less than two retries, retry the search. The first retry will wait two seconds and the
  second will wait four seconds. Incrementing retry will trigger the request effect again. When the
  retry effect is cleaned up, cancel the timer. No manual search button is necessary. This effect does
  not retry other statuses.
  */
  useEffect(() => {
    if (loading || retry >= 2 || !['error', 'timeout', 'provider_error'].includes(search?.status)) return;
    const timer = setTimeout(() => setRetry(count => count + 1), 2000 * (retry + 1));
    return () => clearTimeout(timer);
  }, [loading, search?.status, retry]);

  /* VALIDATE DESTINATION COORDINATES
  
  Before converting a coordinate to a number, reject null, undefined and empty strings. Check that
  both lat and lng are valid numbers using Number(). Ensure they are finite and are in the appropriate
  ranges. Latitude must be in the range -90 to 90 and longitude must be in the range -180 to 180. This
  prevents an empty string or null from being converted to the invented 0,0 coordinate. Other values
  returned by Number() may also pass. This is not a strict type check.
  */
  const valid = destination.lat !== null && destination.lat !== undefined && destination.lat !== '' &&
    destination.lng !== null && destination.lng !== undefined && destination.lng !== '' &&
    Number.isFinite(Number(destination.lat)) && Number.isFinite(Number(destination.lng)) &&
    Math.abs(Number(destination.lat)) <= 90 && Math.abs(Number(destination.lng)) <= 180;

  useEffect(() => {
    /* HANDLE MISSING COORDINATES
    
    If coordinates fail validation, stop loading and store a missing_coordinates result with an empty
    array of hotels and a message. Do not make a hotel request.
    */
    if (!valid) {
      setLoading(false);
      setSearch({ status: 'missing_coordinates', hotels: [], message: 'This destination needs valid coordinates before nearby hotels can be found.' });
      return;
    }
    /* REUSE THE INITIAL HOTEL SEARCH
    
    If the radius is 5000 meters, retry is zero and destination.hotelSearch is truthy then reuse that
    initial hotel search and stop loading without making a request. This prevents a duplicate request by
    reusing the automatic hotel search given with a prediction. The reused search is not checked by the
    HTTP response validation code below. This initial hotel search can also be reused by returning to
    the default radius.
    */
    if (radius === 5000 && retry === 0 && destination.hotelSearch) {
      setSearch(destination.hotelSearch);
      setLoading(false);
      return;
    }
    /* START A HOTEL REQUEST
    
    Create an AbortController, set loading to true and clear the current search. Encode the destination
    coordinates, radius_m and a limit of three into a URLSearchParams. Make a GET request to /api/hotels
    under apiBaseUrl using the controller's signal.
    */
    const controller = new AbortController();
    setLoading(true);
    setSearch(null);
    const params = new URLSearchParams({ lat: destination.lat, lon: destination.lng, radius_m: radius, limit: 3 });
    fetch(`${apiBaseUrl}/api/hotels?${params}`, { signal: controller.signal })
      .then(async response => {
        /* PARSE AND VALIDATE THE RESPONSE
        
        Try to parse the response as JSON. If it fails use null. For an unsuccessful response, throw an
        error with a detail field if the detail is a string or a generic hotel search error message
        otherwise. For a successful response, require the response to have a hotels field that is an array.
        This does not validate the hotels in that array nor does it require the response status to be ok.
        This response can pass and later show a provider-status message.
        */
        const data = await response.json().catch(() => null);
        if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : 'Hotel search could not finish. Please try again later.');
        if (!Array.isArray(data?.hotels)) throw new Error('Hotel search returned an unexpected response.');
        return data;
      })
      /* STORE RESULTS AND HANDLE REQUEST ERRORS
      
      If the response is successful, pass the result to setSearch. If the request fails and has not been
      cancelled, store status error, an empty array of hotels and a message. TypeError responses will use
      the backend-connectivity error message but other errors will use the error message. A TypeError is
      not necessarily a network error. The backend-connectivity error assumes the backend is running on
      port 8000. Do not stop loading in finally unless the request has not been cancelled.
      */
      .then(setSearch)
      .catch(error => {
        if (!controller.signal.aborted) setSearch({ status: 'error', hotels: [], message: error instanceof TypeError ? 'Cannot reach the hotel service. Check that the backend is running on port 8000.' : error.message });
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    /* REQUEST CLEANUP AND DEPENDENCIES
    
    Clean up the request on effect cleanup including unmount or change to any of the following:
    coordinates, hotelSearch, radius, retry, coordinate validity, or apiBaseUrl. Both the loading and
    error handlers check the abort signal. The successful .then(setSearch) handler does not explicitly
    check the signal. Cancellation alone does not guarantee that an already-resolved stale response
    cannot update state.
    */
    return () => controller.abort();
  }, [destination.lat, destination.lng, destination.hotelSearch, radius, retry, valid, apiBaseUrl]);

  /* SELECT UP TO THREE HOTELS WITH PHOTOS
  
  Copy the list of hotels from the search and then filter to only include hotels with a truthy image
  url that has not failed in the current search. Sort the resulting hotels by ascending distance_m and
  keep up to three hotels. This assumes that the hotel data and their distances have the expected
  shape. If a hotel image fails, replacement hotels are not fetched.
  */
  const hotels = [...(search?.hotels || [])].filter(place => place.image && !failedImages.has(place.image)).sort((a, b) => a.distance_m - b.distance_m).slice(0, 3);
  /* FILTER THE SELECTED HOTELS
  
  Filter the three selected hotels by a substring match of the hotel's name, case-insensitively.
  Before matching trim any whitespace from the user's filter text. This is local filtering and makes
  no request to the backend. Because this filtering happens after the limit of three hotels, no other
  hotels can be revealed. This code assumes the hotel.name value is a string.
  */
  const visible = hotels.filter(hotel => hotel.name.toLowerCase().includes(filter.trim().toLowerCase()));

  /* RESULTS SECTION AND HEADER
  
  Show a results section with an accessible label of the destination. Indicate that the results show
  up to three nearby hotels with photos in order of distance. Show search radius options of 1609,
  5000, 16093 and 24140 meters (1 mile, 3.1 miles, 10 miles and 15 miles). Convert the currently
  selected radius to a number before updating state.
  */
  return <section className="hotel-results" aria-label={`Hotels near ${destination.name}`}>
    <div className="hotel-results__head">
      <div><span className="hotel-results__eyebrow">Stay close to the discovery</span><h3>Hotels near {destination.name}</h3><p>Up to three nearby hotels with photos, ordered by distance from this landmark.</p></div>
      <label className="hotel-results__radius">Search radius<select aria-label="Hotel search radius" value={radius} onChange={event => setRadius(Number(event.target.value))}>
        <option value={1609}>1 mile</option><option value={5000}>3.1 miles</option><option value={16093}>10 miles</option><option value={24140}>15 miles</option>
      </select></label>
    </div>
    {/* FILTER CONTROL AND RESULT COUNT
    
    Show an accessible filter input for hotel names. When loading is done and the status is ok, show the
    count of selected hotels with photos (using singular or plural count depending on the number). This
    is the count of hotels prior to filtering by name. Otherwise show Nearby stays.
    */}
    <div className="hotel-results__tools"><label className="hotel-results__filter"><Search size={16}/><input aria-label="Filter hotel names" placeholder="Filter these hotels…" value={filter} onChange={event => setFilter(event.target.value)}/></label>
      <span>{!loading && search?.status === 'ok' ? `${hotels.length} nearby ${hotels.length === 1 ? 'hotel' : 'hotels'}` : 'Nearby stays'}</span>
    </div>
    {/* LOADING, ERROR AND EMPTY STATES
    
    Use aria-live polite for updating results and aria-busy when loading. While loading show three
    skeleton cards and a loading message for screen readers. If the status is not ok then show the
    provided message or a message with role alert. If no matching hotels remain after filtering,
    differentiate between a mismatch on the name filter and no hotels with loadable photos. In the
    latter case suggest a larger search radius. The distinction uses whether any hotels remain before
    the name filter is applied.
    */}
    {/* HOTEL RESULT CARDS
    
    Show each hotel as an article with a key of id. Include the HotelPhoto component and pass the
    callback for failed photos. Convert the distance_m field to miles by dividing by 1609.344 and show
    two decimal places. Show the name and address or Address not supplied if no address is present. Tell
    users to check rates and availability at the hotel. All text in the hotel cards is rendered as text
    by React and is not injected as HTML.
    */}
    <div aria-live="polite" aria-busy={loading}>
      {loading ? <div className="hotel-results__grid">{[1,2,3].map(id => <div className="hotel-results__skeleton" key={id}/>)}<span className="hotel-results__sr-only">Automatically finding nearby hotels…</span></div>
      : search?.status !== 'ok' ? <div className="hotel-results__message"><Hotel size={26}/><p role="alert">{search?.message || 'Hotel search is unavailable.'}</p></div>
      : visible.length === 0 ? <div className="hotel-results__message"><MapPin size={26}/><p>{hotels.length ? 'No hotel names match your filter.' : 'No hotels with loadable photos found here. Try a larger search radius.'}</p></div>
      : <div className="hotel-results__grid">{visible.map(hotel => <article className="hotel-result-card" key={hotel.id}>
          <HotelPhoto hotel={hotel} onFailure={hideFailedImage}/>
          <div className="hotel-result-card__top"><span className="hotel-result-card__icon"><Hotel size={22}/></span><span>{(hotel.distance_m / 1609.344).toFixed(2)} miles away</span></div>
          <h4>{hotel.name}</h4><p>{hotel.address || 'Address not supplied'}</p>
          <small>Rates and availability: check with hotel</small>
          {/* MAP AND WEBSITE LINKS
          
          For Google Maps, the intended search URL uses the hotel's lat and lng and api=1. Although this URL
          is labeled Directions this is a search for a location, not a URL for a route that is calculated by
          this component or a link to a location with a landmark as the origin. For hotel websites, show a
          link if the url matches the intended prefix of HTTP or HTTPS. External links will open in a new tab
          with noopener noreferrer. The Maps link uses a plain URL, and the website prefix check uses a valid
          JavaScript regular expression.
          */}
          <div className="hotel-result-card__links"><a target="_blank" rel="noopener noreferrer" href={`https://www.google.com/maps/search/?api=1&query=${hotel.latitude},${hotel.longitude}`}><MapPin size={13}/> Directions</a>
            {hotel.website && /^https?:\/\//.test(hotel.website) && <a href={hotel.website} target="_blank" rel="noopener noreferrer">Hotel website <ExternalLink size={12}/></a>}
          </div>
        </article>)}</div>}
    </div>
    {/* PROVIDER ATTRIBUTION AND DISTANCE NOTE
    
    Include links to credit Geoapify and OpenStreetMap contributors. The href values for these links are
    plain HTTPS URLs. Indicate that distances are straight-line estimates and that hotels found by the
    search do not necessarily indicate room availability, prices or ratings.
    */}
    <p className="hotel-results__attribution"><a href="https://www.geoapify.com/" target="_blank" rel="noopener noreferrer">Powered by Geoapify</a> · <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© OpenStreetMap contributors</a><br/>Distances are straight-line estimates. Search results do not confirm room availability, prices or ratings.</p>
  </section>;
}
