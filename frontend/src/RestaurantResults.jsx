/* RESTAURANT RESULTS

Use backend search results to display restaurants around a given destination.

For uploaded destinations, use Neon's longitude and latitude to perform the first restaurant search
at /api/predict. For destinations without an initial restaurant search, use radius and retry to make
GET calls to /api/restaurants.

The client does not have access to the Geoapify API key.
*/
/* IMPORTS

Use React for components. useState is used for local state in the component. useEffect is used for
request handling, state resets, retry timers and cleanup. UtensilsCrossed, MapPin, Search and
ExternalLink are lucide-react icons.

The component uses the hotel-results, hotel-result-card and hotel-photo-credit classes which were
defined in hotels.css so that the visual appearance of the restaurant cards is similar to the hotel
cards.
*/
import React, { useEffect, useState } from 'react';
import { UtensilsCrossed, MapPin, Search, ExternalLink } from 'lucide-react';
import './hotels.css';

/* RESTAURANT PHOTO COMPONENT

The RestaurantPhoto component is passed a restaurant object and an onFailure callback from its
parent. The failed state tracks if the restaurant's photo failed to load. failed will be reset to
false whenever the restaurant.image changes.

The React fragment wraps the image and (optionally) attribution block.
*/
function RestaurantPhoto({ restaurant, onFailure }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [restaurant.image]);
  /* LOAD A RESTAURANT PHOTO
  
  If a restaurant has a photo and has not failed to load, render the image.
  
  Use the restaurant name for the image alt text and lazy loading so the browser can defer loading
  until the image approaches the viewport.
  
  Set the referrer policy to no-referrer so no Referer header will be included in the image request.
  
  If the image fails to load, set the image's failed state to true and pass the image's URL to the
  parent. The parent will remove any cards that have this URL from the results list.
  
  If there is no useful photo for a restaurant, display the text Photo unavailable along with the
  UtensilsCrossed icon.
  
  The Photo unavailable text might flash on the page before the parent removes the card associated
  with a failed photo.
  */
  return <><div className="hotel-result-card__photo">
    {restaurant.image && !failed
      ? <img src={restaurant.image} alt={restaurant.name} loading="lazy" referrerPolicy="no-referrer" onError={() => { setFailed(true); onFailure(restaurant.image); }}/>
      : <div className="hotel-result-card__photo-fallback"><UtensilsCrossed size={34}/><span>Photo unavailable</span></div>}
    {/* PHOTO SOURCE LINK
    
    If an unfailed image has an image_source and that value passes the intended https or http prefix
    check, display Photo source and link to the source in a new tab with noopener noreferrer.
    
    The regular expression checks the intended https or http prefix.
    
    Checking the intended https or http prefix does not verify that the site is the intended one.
    */}
    {restaurant.image && !failed && restaurant.image_source && /^https?:\/\//.test(restaurant.image_source) && <a href={restaurant.image_source} target="_blank" rel="noopener noreferrer">Photo source</a>}
  </div>
    {/* WIKIMEDIA COMMONS ATTRIBUTION
    
    If the image has an image_provider of Wikimedia Commons and has not failed to load, display a source
    link labeled with the image title or fallback title, the author and license.
    
    If the image has an image_license_url, render the license as a link. Otherwise, render it as plain
    text.
    
    Display that the photo is from Wikimedia Commons and has been cropped to fit.
    
    React will render the image's title, author and license as plain text.
    
    The attribution block does not independently verify the link URLs.
    */}
    {restaurant.image && !failed && restaurant.image_provider === 'Wikimedia Commons' && <div className="hotel-photo-credit">
      <a href={restaurant.image_source} target="_blank" rel="noopener noreferrer">{restaurant.image_title || 'Restaurant photo'}</a>
      <span>Photo: {restaurant.image_author}</span>
      {restaurant.image_license_url
        ? <a href={restaurant.image_license_url} target="_blank" rel="noopener noreferrer">{restaurant.image_license}</a>
        : <span>{restaurant.image_license}</span>}
      <span>Wikimedia Commons · cropped to fit</span>
    </div>}
  </>;
}

/* COMPONENT INPUTS

The RestaurantResults component is passed a destination and apiBaseUrl from a parent. The
destination is passed the destination's name, its latitude in lat, longitude in lng and (optionally)
a restaurantSearch. A destination object is expected to exist.
*/
/* SCOPE OF THIS COMPONENT

This component loads, filters and displays restaurant results and photo attribution. Backend
services provide restaurant search, distance estimation, photo matching, provider information and
server-side caching.

These comments explain the code provided. Markdown corruption in the pasted JSX, URLs and regular
expressions has been restored.
*/
export default function RestaurantResults({ destination, apiBaseUrl }) {
  /* LOCAL STATE
  
  radius starts at 5000 meters.
  
  search starts as destination.restaurantSearch if that is truthy, otherwise null.
  
  loading starts as true only if there was not a truthy initial restaurantSearch.
  
  filter starts as an empty string and is used for local filtering on the restaurant name.
  
  retry starts as zero and is used for automatic retries.
  
  failedImages starts as an empty Set of images that have failed to load.
  */
  const [radius, setRadius] = useState(5000);
  const [search, setSearch] = useState(destination.restaurantSearch || null);
  const [loading, setLoading] = useState(!destination.restaurantSearch);
  const [filter, setFilter] = useState('');
  const [retry, setRetry] = useState(0);
  const [failedImages, setFailedImages] = useState(() => new Set());

  /* TRACK FAILED IMAGES
  
  failedImages is reset whenever search changes.
  
  When an image fails to load create a new failedImages Set with the previous failed images and the
  URL of the image that has failed. React needs a new Set to observe the change in state.
  
  If multiple restaurants have failed images with the same URL, then all cards associated with that
  URL are removed from the results.
  */
  useEffect(() => setFailedImages(new Set()), [search]);
  const hideFailedImage = url => setFailedImages(previous => new Set([...previous, url]));

  /* RESET FOR A NEW DESTINATION
  
  When either the latitude or longitude changes, reset retry to zero and reset the restaurant-name
  filter.
  
  This does not happen when the restaurantSearch, apiBaseUrl, radius or coordinate validity changes.
  
  Therefore radius changes do not result in a new retry count in this effect.
  */
  useEffect(() => {
    setRetry(0);
    setFilter('');
  }, [destination.lat, destination.lng]);

  /* AUTOMATIC RETRIES
  
  After loading has completed, for retry searches with status of error, timeout or provider_error and
  fewer than two retries, retry the search.
  
  Wait 2 seconds for the first retry and 4 seconds for the second.
  
  When retry increases the request effect will occur again.
  
  Clean up the timer when the retry effect is cleaned up.
  
  This effect does not retry searches with other status values. A manual search button is not
  required.
  */
  useEffect(() => {
    if (loading || retry >= 2 || !['error', 'timeout', 'provider_error'].includes(search?.status)) return;
    const timer = setTimeout(() => setRetry(count => count + 1), 2000 * (retry + 1));
    return () => clearTimeout(timer);
  }, [loading, search?.status, retry]);

  /* VALIDATE DESTINATION COORDINATES
  
  Before conversion to numbers reject null, undefined and empty-string values.
  
  Use Number() to verify that both values are finite and in the appropriate ranges.
  
  Latitude should be between -90 and 90 and longitude between -180 and 180.
  
  This prevents null and empty strings from being converted into an assumed 0,0 location.
  
  Other values that Number() can handle may still pass.
  */
  const valid = destination.lat !== null && destination.lat !== undefined && destination.lat !== '' &&
    destination.lng !== null && destination.lng !== undefined && destination.lng !== '' &&
    Number.isFinite(Number(destination.lat)) && Number.isFinite(Number(destination.lng)) &&
    Math.abs(Number(destination.lat)) <= 90 && Math.abs(Number(destination.lng)) <= 180;

  useEffect(() => {
    /* HANDLE MISSING COORDINATES
    
    If validation fails then stop loading and set the result to missing_coordinates with an empty
    restaurants array and a message. Do not make a restaurant request.
    */
    if (!valid) {
      setLoading(false);
      setSearch({ status: 'missing_coordinates', restaurants: [], message: 'This destination needs valid coordinates before nearby restaurants can be found.' });
      return;
    }
    /* REUSE THE INITIAL RESTAURANT SEARCH
    
    If the radius is 5000 meters, retry is zero and destination.restaurantSearch is truthy then use that
    initial restaurant search and stop loading without requesting new data.
    
    This avoids duplicating the restaurant search that comes with a prediction.
    
    The reused value is not validated by the HTTP response-validation path.
    
    Returning to the default radius value can also reuse this initial restaurant search.
    */
    if (radius === 5000 && retry === 0 && destination.restaurantSearch) {
      setSearch(destination.restaurantSearch);
      setLoading(false);
      return;
    }
    /* START A RESTAURANT REQUEST
    
    Create an AbortController. Set loading to true and clear the current search.
    
    Use URLSearchParams to encode the destination coordinates, radius_m and limit of three.
    
    Make a GET request to /api/restaurants under apiBaseUrl with the signal from the AbortController.
    */
    const controller = new AbortController();
    setLoading(true);
    setSearch(null);
    const params = new URLSearchParams({ lat: destination.lat, lon: destination.lng, radius_m: radius, limit: 3 });
    fetch(`${apiBaseUrl}/api/restaurants?${params}`, { signal: controller.signal })
      .then(async response => {
        /* PARSE AND VALIDATE THE RESPONSE
        
        Try to parse the response as JSON and use null if it fails.
        
        For unsuccessful responses throw an error with a detail string if available, otherwise throw a
        generic restaurant-search error message.
        
        For successful responses verify that the value of restaurants is an array.
        
        This does not verify individual restaurants or verify response status of ok.
        
        A response might pass this check and still show a provider-status message later.
        */
        const data = await response.json().catch(() => null);
        if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : 'Restaurant search could not finish. Please try again later.');
        if (!Array.isArray(data?.restaurants)) throw new Error('Restaurant search returned an unexpected response.');
        return data;
      })
      /* STORE RESULTS AND HANDLE REQUEST ERRORS
      
      If the response is successful, pass it to setSearch.
      
      If the request fails and has not been aborted store status as error, an empty array for restaurants
      and a message. TypeErrors get the backend-connectivity message. All other errors use the error's
      message. A TypeError does not necessarily mean that there is a connectivity problem.
      
      The connectivity message assumes that the backend is running on port 8000.
      
      Only stop loading in finally if the request has not been aborted.
      */
      .then(setSearch)
      .catch(error => {
        if (!controller.signal.aborted) setSearch({ status: 'error', restaurants: [], message: error instanceof TypeError ? 'Cannot reach the restaurant service. Check that the backend is running on port 8000.' : error.message });
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    /* REQUEST CLEANUP AND DEPENDENCIES
    
    Abort the request when the effect is cleaned up. This could occur when the component is unmounted or
    when the destination's coordinates, restaurantSearch, radius, retry, coordinate validity or
    apiBaseUrl changes.
    
    The error and loading handlers check the abort signal.
    
    The successful .then(setSearch) handler does not check the abort signal so cancellation alone does
    not prevent a stale response from being used after it has been resolved.
    */
    return () => controller.abort();
  }, [destination.lat, destination.lng, destination.restaurantSearch, radius, retry, valid, apiBaseUrl]);

  /* SELECT UP TO THREE RESTAURANTS WITH PHOTOS
  
  Copy the restaurants array from the search and filter to only include restaurants with a truthy
  image URL that are not failed in the current search.
  
  Sort the restaurants by distance_m in ascending order and only keep the top three.
  
  This assumes that the restaurants and their distances have the expected shape.
  
  This does not replace a failed photo with another photo.
  */
  const restaurants = [...(search?.restaurants || [])].filter(place => place.image && !failedImages.has(place.image)).sort((a, b) => a.distance_m - b.distance_m).slice(0, 3);
  /* FILTER THE SELECTED RESTAURANTS
  
  Filter the top three restaurants by using a case-insensitive substring match on restaurant name.
  
  Trim the filter text before matching.
  
  This is a local filter and does not make a new request.
  
  Because filtering is done after the three-restaurant limit, it cannot reveal additional restaurants.
  
  This assumes that restaurant.name is a string.
  */
  const visible = restaurants.filter(restaurant => restaurant.name.toLowerCase().includes(filter.trim().toLowerCase()));

  /* RESULTS SECTION AND HEADER
  
  Display a section with an accessible label that describes the destination.
  
  Display a message that up to three restaurants with photos are listed in order by distance.
  
  Provide search radii of 1609, 5000, 16093 and 24140 meters which can be described as 1 mile, 3.1
  miles, 10 miles and 15 miles respectively.
  
  Convert the selected radius to a number before updating state.
  */
  return <section className="hotel-results" aria-label={`Restaurants near ${destination.name}`}>
    <div className="hotel-results__head">
      <div><span className="hotel-results__eyebrow">Taste the neighborhood</span><h3>Restaurants near {destination.name}</h3><p>Up to three nearby restaurants with photos, ordered by distance from this landmark.</p></div>
      <label className="hotel-results__radius">Search radius<select aria-label="Restaurant search radius" value={radius} onChange={event => setRadius(Number(event.target.value))}>
        <option value={1609}>1 mile</option><option value={5000}>3.1 miles</option><option value={16093}>10 miles</option><option value={24140}>15 miles</option>
      </select></label>
    </div>
    {/* FILTER CONTROL AND RESULT COUNT
    
    Provide an accessible way to filter restaurants by name.
    
    When loading has completed and status is ok show the number of restaurants with photos that have
    been selected. Use appropriate singular or plural wording.
    
    This value is the number of restaurants without the name filter applied.
    
    Otherwise display Nearby dining.
    */}
    <div className="hotel-results__tools"><label className="hotel-results__filter"><Search size={16}/><input aria-label="Filter restaurant names" placeholder="Filter these restaurants…" value={filter} onChange={event => setFilter(event.target.value)}/></label>
      <span>{!loading && search?.status === 'ok' ? `${restaurants.length} nearby ${restaurants.length === 1 ? 'restaurant' : 'restaurants'}` : 'Nearby dining'}</span>
    </div>
    {/* LOADING, ERROR AND EMPTY STATES
    
    Use aria-busy while loading and aria-live polite for updates to the results.
    
    During loading display three skeleton restaurant cards and screen-reader loading text.
    
    If status is not ok display the provided message or a fallback with role alert.
    
    If no restaurants with loadable photos remain distinguish between no restaurants with loadable
    photos and a name filter mismatch. For the former, suggest a larger radius.
    */}
    {/* RESTAURANT RESULT CARDS
    
    Render each restaurant as an article with a React key matching the restaurant's id.
    
    Include the RestaurantPhoto component with the failed-image callback.
    
    Convert distance_m to miles by dividing by 1609.344 and use two decimal places.
    
    Display the restaurant name and address or Address not supplied.
    
    Tell the user to check hours and menus with the restaurant.
    
    The cards do not display opening hours, prices or cuisine from the restaurant search.
    
    React will render these values as plain text rather than HTML.
    */}
    <div aria-live="polite" aria-busy={loading}>
      {loading ? <div className="hotel-results__grid">{[1,2,3].map(id => <div className="hotel-results__skeleton" key={id}/>)}<span className="hotel-results__sr-only">Automatically finding nearby restaurants…</span></div>
      : search?.status !== 'ok' ? <div className="hotel-results__message"><UtensilsCrossed size={26}/><p role="alert">{search?.message || 'Restaurant search is unavailable.'}</p></div>
      : visible.length === 0 ? <div className="hotel-results__message"><MapPin size={26}/><p>{restaurants.length ? 'No restaurant names match your filter.' : 'No restaurants with loadable photos found here. Try a larger search radius.'}</p></div>
      : <div className="hotel-results__grid">{visible.map(restaurant => <article className="hotel-result-card" key={restaurant.id}>
          <RestaurantPhoto restaurant={restaurant} onFailure={hideFailedImage}/>
          <div className="hotel-result-card__top"><span className="hotel-result-card__icon"><UtensilsCrossed size={22}/></span><span>{(restaurant.distance_m / 1609.344).toFixed(2)} miles away</span></div>
          <h4>{restaurant.name}</h4><p>{restaurant.address || 'Address not supplied'}</p>
          <small>Menu and hours: check with restaurant</small>
          {/* MAP AND WEBSITE LINKS
          
          The intended Google Maps link uses api=1 and uses the latitude and longitude of the restaurant.
          
          Although this is labeled Directions it is actually a location search rather than a directions URL
          using a landmark as an origin or a route created by this component.
          
          If a restaurant has a website and that URL passes the intended https or http prefix check, display a
          link to the restaurant's website.
          
          External links open in a new tab with noopener noreferrer.
          
          The Maps link uses a plain URL, and the website prefix check uses a valid JavaScript regular
          expression.
          */}
          <div className="hotel-result-card__links"><a target="_blank" rel="noopener noreferrer" href={`https://www.google.com/maps/search/?api=1&query=${restaurant.latitude},${restaurant.longitude}`}><MapPin size={13}/> Directions</a>
            {restaurant.website && /^https?:\/\//.test(restaurant.website) && <a href={restaurant.website} target="_blank" rel="noopener noreferrer">Restaurant website <ExternalLink size={12}/></a>}
          </div>
        </article>)}</div>}
    </div>
    {/* PROVIDER ATTRIBUTION AND DISTANCE NOTE
    
    Credit Geoapify and OpenStreetMap contributors with external links.
    
    The attribution href values use plain https URLs.
    
    Tell the user that the distance is an estimate and encourage them to check current opening hours,
    prices and menus with the restaurant.
    */}
    <p className="hotel-results__attribution"><a href="https://www.geoapify.com/" target="_blank" rel="noopener noreferrer">Powered by Geoapify</a> · <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© OpenStreetMap contributors</a><br/>Distances are straight-line estimates. Check current menus, prices and opening hours with the restaurant.</p>
  </section>;
}
