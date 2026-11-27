/*
 * AUTOMATIC AIRPORT LOOKUP
 * Autoload an airport using the location of the point of interest.
 * AirportResults shows an airport near the point of interest as provided by the backend.
 * The user can switch between all airports and international airports only.
 */

/*
 * IMPORTS
 * React is used as the building block for the component. useState is used for local state
 * used by the UI, and useEffect is used for requests, retry intervals and cleanup based on
 * changes to dependencies.
 * Plane, MapPin and ExternalLink are icons provided by lucide-react.
 */
import React, { useEffect, useState } from 'react';
import { Plane, MapPin, ExternalLink } from 'lucide-react';

/*
 * EMBEDDED STYLES
 * The embedded CSS for the component is provided in AIRPORT_STYLES as a template literal.
 * Styles are provided for the results card, header, select element for airport selection,
 * loading indicator, airport name and codes, distance, links and information notes.
 * Media queries are provided for screens up to 680px in width.
 * Reduced motion is applied if requested to remove animation from the loading indicator.
 */
const AIRPORT_STYLES = `
.airport-results{margin:24px 0;padding:28px;border:1px solid rgba(255,255,255,.13);border-radius:24px;background:linear-gradient(130deg,rgba(44,65,89,.45),rgba(20,23,35,.75));color:#f5f7fc}
.airport-results__head{display:flex;justify-content:space-between;align-items:flex-start;gap:20px}
.airport-results__eyebrow{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#94cff4;font-weight:700}
.airport-results h3{margin:8px 0;font-size:26px;line-height:1.2}
.airport-results p{color:#b9c6d9;font-size:14px;line-height:1.6;margin:8px 0}
.airport-results__select{display:grid;gap:7px;color:#bac8da;font-size:12px;flex-shrink:0}
.airport-results select{padding:10px 12px;border-radius:12px;border:1px solid #46536a;background:#172436;color:white;font:inherit;max-width:100%}
.airport-results__body{display:flex;gap:20px;align-items:center;margin-top:22px}
.airport-results__icon{display:grid;place-items:center;width:64px;height:64px;flex-shrink:0;background:#233e55;border:1px solid #3c6079;border-radius:18px;color:#a7d9fa}
.airport-results h4{font-size:23px;line-height:1.3;margin:0 0 6px;overflow-wrap:anywhere}
.airport-results__code{display:inline-block;font-size:13px;letter-spacing:.06em;padding:4px 8px;margin-left:9px;border-radius:7px;background:#29485f;color:#bfe5ff;vertical-align:middle}
.airport-results__distance{margin-left:auto;text-align:right;flex-shrink:0}
.airport-results__distance strong{display:block;font-size:28px;line-height:1.4;color:#f5f7fc}
.airport-results__distance span{font-size:12px;color:#afc2d8}
.airport-results__links{display:flex;flex-wrap:wrap;gap:18px;margin-top:18px}
.airport-results a{display:inline-flex;align-items:center;gap:6px;color:#a7d9fa;font-size:13px;text-decoration:underline;text-underline-offset:3px}
.airport-results a:hover{color:white}
.airport-results__note{font-size:12px!important;margin-top:18px!important}
.airport-results__loading{display:flex;align-items:center;gap:12px;margin:24px 0;color:#c1d7ea}
.airport-results__loading svg{animation:airport-pulse 1.4s ease-in-out infinite}
@keyframes airport-pulse{50%{opacity:.35;transform:translateX(5px)}}
@media(prefers-reduced-motion:reduce){.airport-results__loading svg{animation:none}}
@media(max-width:680px){.airport-results{padding:20px}.airport-results__head{flex-direction:column}.airport-results__body{flex-wrap:wrap}.airport-results__body>div:nth-child(2){flex:1;min-width:180px}.airport-results__distance{margin-left:0;text-align:left}.airport-results h3{font-size:23px}}
`;

/*
 * COMPONENT INPUTS
 * The component receives a destination and apiBaseUrl from its parent.
 * name from destination is used in the header and accessible section.
 * latitude from destination.lat and longitude from destination.lng are used.
 * A destination is expected to be provided.
 */
export default function AirportResults({ destination, apiBaseUrl }) {
  /*
   * LOCAL STATE
   * internationalOnly is used to determine the type of airports to load and defaults to
   * false.
   * result will store either the result from the backend or a local error object.
   * loading is used to determine whether a loading indicator is shown and defaults to true.
   * retry is used to track the number of automatic retries and defaults to zero.
   */
  const [internationalOnly, setInternationalOnly] = useState(false);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const lat = destination.lat;
  const lon = destination.lng;
  /*
   * VALIDATE COORDINATES
   * Both coordinates are required and must not be empty strings.
   * They will be converted using Number() for validation and must be finite.
   * Latitude must have an absolute value less than or equal to 90. Longitude must have an
   * absolute value less than or equal to 180.
   * The value of lat and lon are not changed by the validation.
   * Coercion to numbers is performed here so it does not enforce only numbers or number-
   * strings to be provided. Validation is performed on the backend.
   */
  const valid = lat !== null && lat !== undefined && lat !== '' &&
    lon !== null && lon !== undefined && lon !== '' &&
    Number.isFinite(Number(lat)) && Number.isFinite(Number(lon)) &&
    Math.abs(Number(lat)) <= 90 && Math.abs(Number(lon)) <= 180;

  /*
   * RESET RETRY COUNT
   * retry will be reset to zero if there is a change in lat, lon or internationalOnly.
   * This allows the next point or search type a separate retry count.
   * A change in apiBaseUrl will trigger a request, but not a reset of the retry count in
   * this effect.
   */
  useEffect(() => setRetry(0), [lat, lon, internationalOnly]);

  /*
   * REQUEST EFFECT DEPENDENCIES
   * The request effect will be run again if any of lat, lon, internationalOnly, retry, valid
   * or apiBaseUrl change.
   * Each run of the effect will clean up the previous request before running the new effect.
   */
  useEffect(() => {
    /*
     * HANDLE MISSING COORDINATES
     * If coordinates are not valid, stop loading and show a message for missing_coordinates
     * instead of requesting an airport.
     */
    if (!valid) {
      setLoading(false);
      setResult({ status: 'missing_coordinates', message: 'This landmark needs coordinates before its closest airport can be found.' });
      return;
    }
    /*
     * REQUEST CANCELLATION
     * An AbortController will be created for each request that is valid.
     * The request will be aborted when the request effect is cleaned up, including during
     * changes to dependencies and unmounting of the component.
     * The signal will be checked prior to setting the request’s results, errors or loading
     * state so an aborted request does not overwrite an active search.
     */
    const controller = new AbortController();
    /*
     * START A NEW SEARCH
     * loading will be set to true and the previous result will be removed.
     * lat, lon and international_only will be encoded using URLSearchParams.
     * international_only will be encoded as either true or false depending on the boolean
     * value.
     * A GET request will be made to /api/airports using the provided apiBaseUrl.
     * A Geoapify API key will not be sent in this request.
     */
    setLoading(true);
    setResult(null);
    const params = new URLSearchParams({ lat, lon, international_only: String(internationalOnly) });
    fetch(`${apiBaseUrl}/api/airports?${params}`, { signal: controller.signal })
      /*
       * PARSE THE HTTP RESPONSE
       * Try to parse the response as JSON. If failed, use null.
       * If the request was not successful, use a detail message if available, otherwise use
       * the generic airport-search message.
       * HTTP status codes of 500 or higher are considered retryable.
       * This branch does not automatically mark 4xx status codes as retryable.
       */
      .then(async response => {
        const data = await response.json().catch(() => null);
        if (!response.ok) {
          const error = new Error(typeof data?.detail === 'string' ? data.detail : 'Airport search could not finish.');
          error.retryable = response.status >= 500;
          throw error;
        }
        /*
         * PROVIDER STATUS RESPONSES
         * A response with a non-ok status will be treated as Unexpected airport response
         * even if the HTTP status was successful.
         * This does not preserve the provider-specific message from the response.
         * Such a response is not automatically considered retryable.
         */
        if (data?.status !== 'ok' || !Object.hasOwn(data, 'airport')) throw new Error('Unexpected airport response.');
        /*
         * VALIDATE RESPONSE STRUCTURE
         * status must be equal to ok and the response must contain an airport property.
         * A null airport is acceptable and indicates a search has been completed but no
         * airport was found.
         * If an airport value exists, then the name must be truthy and the distance_m must
         * be a finite number.
         * This does not validate all fields on an airport object, nor its coordinates or the
         * non-negativity of the distance.
         */
        if (data.airport && (!data.airport.name || !Number.isFinite(data.airport.distance_m))) throw new Error('Incomplete airport response.');
        return data;
      })
      /*
       * STORE RESULTS AND HANDLE ERRORS
       * Only store valid data if the request has not been aborted.
       * For errors that are caught, status will be set to error and the error information
       * will be provided.
       * A TypeError will be considered retryable and the cannot-reach-service message will
       * be shown.
       * TypeErrors commonly occur during network failures, but not all TypeErrors indicate
       * network problems.
       * The retryable flag for HTTP server errors is preserved.
       * loading will be set to false when the active request has completed.
       */
      .then(data => { if (!controller.signal.aborted) setResult(data); })
      .catch(error => {
        if (!controller.signal.aborted) setResult({ status: 'error', retryable: error instanceof TypeError || error.retryable,
          message: error instanceof TypeError ? 'Cannot reach the airport service. Check that the backend is running.' : error.message });
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [lat, lon, internationalOnly, retry, valid, apiBaseUrl]);

  /*
   * AUTOMATIC RETRIES
   * A new request will only be made if loading has completed, the current error is retryable
   * and fewer than two retries have occurred.
   * After the first failed request, wait two seconds. After the second failed request wait
   * four seconds. Upon incrementing the retry count, the request effect will run.
   * The timer will be cleared when the retry effect is cleaned up.
   * This results in one attempt and up to two automatic retries for a stable search
   * experience. There is no button to manually trigger a retry in this component.
   */
  useEffect(() => {
    if (loading || !result?.retryable || retry >= 2) return;
    const timer = setTimeout(() => setRetry(count => count + 1), 2000 * (retry + 1));
    return () => clearTimeout(timer);
  }, [loading, result, retry]);

  /*
   * CURRENT AIRPORT
   * airport will be pulled from result if available.
   * If an error has occurred or an airport is being loaded, airport will not be present
   * because the result will either have been cleared or replaced with an error object.
   */
  const airport = result?.airport;
  /*
   * GOOGLE MAPS DIRECTIONS LINK
   * The intended directions URL uses Google’s maps directions format with api=1.
   * origin should be the latitude and longitude of the point of interest. destination should
   * be the latitude and longitude of the airport.
   * This link will be used for external navigation, not a calculated path or with a Google
   * Maps API key.
   * The pasted Markdown formatting has been restored to a plain directions URL for use in
   * JSX.
   */
  const directions = airport ? `https://www.google.com/maps/dir/?api=1&origin=${lat},${lon}&destination=${airport.latitude},${airport.longitude}` : '';
  /*
   * ACCESSIBLE RESULTS SECTION
   * A section will be rendered with the name of the provided destination.
   * AIRPORT_STYLES will be added to the section with a style tag.
   * Where this section is rendered in the Trip Canvas is determined by the parent.
   */
  return <section className="airport-results" aria-label={`Closest airport to ${destination.name}`}>
    <style>{AIRPORT_STYLES}</style>
    {/*
     * HEADER AND AIRPORT SELECTOR
     * The header will either show closest airport or closest international airport.
     * A note will be provided that the airport lookup uses the location of the point of
     * interest.
     * The select element will be bound to a string representation of internationalOnly.
     * When the option changes, a string of true will be converted to a boolean.
     * Changing the option will trigger a new request.
     * The text label provided is the type of airport returned by the provider and does not
     * imply that it is the closest usable passenger airport globally.
     */}
    <div className="airport-results__head">
      <div><span className="airport-results__eyebrow">Getting there</span>
        <h3>{internationalOnly ? 'Closest international airport' : 'Closest airport'} to {destination.name}</h3>
        <p>Automatically found using this landmark’s location.</p>
      </div>
      <label className="airport-results__select">Airport type
        <select value={String(internationalOnly)} onChange={event => setInternationalOnly(event.target.value === 'true')}>
          <option value="false">All airports</option><option value="true">International airports only</option>
        </select>
      </label>
    </div>
    {/*
     * LOADING AND EMPTY STATES
     * aria-live=polite will be used to announce new content and aria-busy will be used while
     * loading.
     * A loading indicator with a plane icon and loading text will be displayed during a
     * request.
     * If an airport is not available, either the result message or a fallback message will
     * be displayed.
     * If the status stored locally is error then role=alert will be used.
     */}
    <div aria-live="polite" aria-busy={loading}>
      {loading ? <div className="airport-results__loading"><Plane size={24}/><span>Finding the closest airport…</span></div>
        : !airport ? <p role={result?.status === 'error' ? 'alert' : undefined}>{result?.message || 'No airport was returned for this location.'}</p>
        : <>
          <div className="airport-results__body">
            <div className="airport-results__icon"><Plane size={30}/></div>
            {/*
             * AIRPORT NAME AND IDENTIFIERS
             * english_name is preferred as the primary airport name, otherwise name will be
             * used.
             * IATA code will be shown as a badge if available.
             * If the english_name differs from the name of the airport then the name of the
             * airport will be shown below the english_name. If an address and ICAO code are
             * available they will also be shown.
             * These values will be rendered by React as plain text and not HTML.
             */}
            <div><h4>{airport.english_name || airport.name}{airport.iata && <span className="airport-results__code">{airport.iata}</span>}</h4>
              {airport.english_name && airport.english_name !== airport.name && <p>{airport.name}</p>}
              <p>{airport.address}</p>
              {airport.icao && <p>ICAO: {airport.icao}</p>}
            </div>
            {/*
             * DISTANCE DISPLAY
             * distance_m will be converted to miles by dividing by 1609.344 and displayed
             * with one decimal place.
             * The distance will be labeled as straight-line distance from the point of
             * interest.
             * The distance value displayed here is from the estimate provided by the backend
             * using the facility and coordinate data, and not from the Google Maps
             * directions URL.
             */}
            <div className="airport-results__distance"><strong>{(airport.distance_m / 1609.344).toFixed(1)} miles</strong><span>from the landmark · straight-line</span></div>
          </div>
          {/*
           * DIRECTIONS AND WEBSITE LINKS
           * Directions will be opened in a new tab with target=_blank and rel=noopener
           * noreferrer.
           * If a website is provided and passes the intended HTTP/HTTPS prefix validation
           * then the airport website link will be provided.
           * The website regular expression has been restored from the pasted Markdown to an
           * HTTP/HTTPS prefix check.
           * A prefix check does not verify the contents of the website. Additional URL
           * validation occurs on the airport service backend.
           */}
          <div className="airport-results__links">
            <a href={directions} target="_blank" rel="noopener noreferrer"><MapPin size={15}/> Directions from landmark</a>
            {airport.website && /^https?:\/\//.test(airport.website) && <a href={airport.website} target="_blank" rel="noopener noreferrer">Airport website <ExternalLink size={14}/></a>}
          </div>
          {/*
           * AIRPORT SERVICE NOTE
           * The location provided is for a mapped airport facility and not a road or a
           * terminal.
           * The all-airports option may contain small or private airports so passenger
           * service should be verified prior to flight planning.
           */}
          <p className="airport-results__note">Distance uses the mapped airport location, not a terminal or road route. All airports can include small or private airfields; confirm passenger service before planning flights.</p>
        </>}
    </div>
    {/*
     * PROVIDER ATTRIBUTION
     * Links will be provided to acknowledge OpenStreetMap and Geoapify contributors.
     * These links will open in a new tab with noopener noreferrer.
     * The pasted Markdown attribution links have been restored to plain HTTPS URLs in the
     * JSX.
     */}
    <p className="airport-results__note"><a href="https://www.geoapify.com/" target="_blank" rel="noopener noreferrer">Powered by Geoapify</a> · <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© OpenStreetMap contributors</a></p>
  </section>;
}
/*
 * SCOPE OF THIS FILE
 * This component will request and display links to external websites and airport
 * information.
 * Airport filtering, distance calculation, access to Geoapify and server side caching are
 * provided by the backend. These comments describe the component without changing its
 * executable logic.
 */
