# AUTOMATIC NEARBY RESTAURANT SEARCH
#
# Search nearby restaurants using Geoapify and Wikimedia Commons.


# IMPORTS
# hashlib can be used to create cache keys based on API key. math can be used
# to check coordinates as well as get distances. os can be used to load config
# files and threading can be used to avoid races on the cache. time can be used
# to get monotonic deadlines and expire times. OrderedDict can be used to store
# the cache in a certain order. Path can be used to load config files and this
# module. urlparse can be used to check that website links are valid.
#
# enrich_hotel_photos takes a list of places, searches Wikimedia Commons,
# and adds image information to the places that were matched.
#
# httpx can be used to make a request to a provider. load_dotenv can be used to
# load a config file for this module.
import hashlib
import math
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlparse
from hotel_photos import enrich_hotel_photos

import httpx
from dotenv import load_dotenv

# LOAD GEOAPIFY CONFIGURATION
# We want to keep our Geoapify credentials separate from the current database
# and admin .env files. We can load this file next to this module (regardless
# of the current working directory). This file will only contain the key
# GEOAPIFY_API_KEY. We can then load next to this module the file .env.geoapify
# with override=True. This will allow keys in this file to override any
# environment variables with the same key.
load_dotenv(Path(__file__).resolve().with_name(".env.geoapify"), override=True)

# BACKEND DEFAULT KEY
# This key is only used in the backend for this project. It can be overridden by
# environment configuration. Do not copy this module or the key in it into
# frontend/src. Instead import _DEFAULT_API_KEY from hotels_service. The
# get_restaurants() function will try to use a non-blank value of GEOAPIFY_API_KEY
# before falling back to this key.
from hotels_service import _DEFAULT_API_KEY

# SHARED SEARCH CACHE
# The key is stored on the backend only and never sent to React. A cache is
# used to ensure that if a search results are re-uploaded/planed, another API
# request is not made. The cache is stored in memory and reads and writes are
# protected by a lock. The normal cache time out is 600 seconds. Network
# requests are not done under the lock, so it is possible for multiple cache
# misses to result in duplicate work.
_cache = OrderedDict()
_cache_lock = threading.Lock()
CACHE_SECONDS = 600


# STANDARD RESPONSE
# _response() will return a response that has the following fields in a consistent
# format. These are status, message, restaurants, center, radius, cache,
# provider and attribution. If no restaurants are passed in an empty list will
# be used instead.
def _response(status, message, center=None, radius_m=5000, restaurants=None, cached=False):
    return {
        "status": status,
        "message": message,
        "restaurants": restaurants if restaurants is not None else [],
        "center": center,
        "radius_m": radius_m,
        "cached": cached,
        "provider": "Geoapify",
        "attribution": "Powered by Geoapify | © OpenStreetMap contributors",
    }


# VALIDATE WEBSITE LINKS
# We only want to return normal website links that users can safely click on.
# We will accept strings up to 2048 characters in length that start with HTTPS
# or HTTP, have a hostname and contain no user or password information.
#
# If an invalid value or an error in parsing a URL is encountered return None.
#
# This does not check the validity of the content of a website only the
# validity of the URL.
def _website(value):

    if not isinstance(value, str) or len(value) > 2048:
        return None
    try:
        parsed = urlparse(value)
        if parsed.scheme in ("https", "http") and parsed.hostname and not parsed.username and not parsed.password:
            return value
    except ValueError:
        pass
    return None


# STRAIGHT-LINE DISTANCE
# Straight line distance (not driving or walking distance)
#
# _distance_m() uses the haversine formula with a 6371000 meter radius for the
# earth. The intermediate haversine value is clamped to prevent rounding issues and
# the final distance is rounded to meters.
def _distance_m(lat1, lon1, lat2, lon2):

    a, b = math.radians(lat1), math.radians(lat2)
    term = math.sin((b - a) / 2) ** 2
    term += math.cos(a) * math.cos(b) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return round(6371000 * 2 * math.asin(math.sqrt(min(1, max(0, term)))))


# RESTAURANT SEARCH ENTRY POINT
# Return a list of restaurants or an unavailable option while preserving
# recognition. Uploads will use Neon for longitude and latitude values. A
# preset destination as well as a change in the radius can use this service through
# the endpoint GET /api/restaurants. This module provides the search function while
# the endpoint is in another module.
def get_restaurants(lat, lon, radius_m=5000, limit=3):





    # VALIDATE DESTINATION COORDINATES
    # Reject missing, blank, non-numeric or out of range/inf coordinates. Convert
    # to floats and then require latitude in the range -90 to 90 and longitude in
    # the range -180 to 180. Return missing_coordinates if any of these errors
    # are handled.
    try:
        if lat is None or lon is None or lat == "" or lon == "":
            raise ValueError()
        latitude, longitude = float(lat), float(lon)
        if not (math.isfinite(latitude) and math.isfinite(longitude)):
            raise ValueError()
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError()
    except (ValueError, TypeError, OverflowError):
        return _response("missing_coordinates", "This landmark has no valid coordinates for restaurant search.")
    # VALIDATE RADIUS AND LIMIT
    # Require radius_m and limit to be integers. Booleans are not accepted.
    # Accept a radius between 500 and 25000 meters. Accept a limit from 1 to 20.
    #
    # Return invalid_search if an invalid value is provided.
    if type(radius_m) is not int or not 500 <= radius_m <= 25000 or type(limit) is not int or not 1 <= limit <= 20:
        return _response("invalid_search", "Use a radius of 500–25,000 meters and a limit of 1–20 restaurants.")

    # CAP NUMBER OF RESTAURANTS RETURNED
    # Return up to three restaurants with matching photos from the restaurants
    # that were matched during the search. After validating the limit reduce it so it
    # is no more than three. Create a response center using the validated
    # destination coordinates.
    limit = min(limit, 3)
    center = {"latitude": latitude, "longitude": longitude}
    # SELECT API KEY
    # Get the value of GEOAPIFY_API_KEY and remove whitespace. If none is provided
    # use the backend default. If neither provides a valid key return not_configured.
    #
    # Do not return the key in the response to the frontend.
    api_key = os.getenv("GEOAPIFY_API_KEY", "").strip() or _DEFAULT_API_KEY
    if not api_key:
        return _response("not_configured", "Add GEOAPIFY_API_KEY to backend-integration/.env.geoapify and restart the backend.", center, radius_m)
    # CACHE IDENTITY
    # Use a SHA256 hash of the API key, coordinates (as validated floats), capped
    # limit, and radius to create a unique cache key. Do not use the raw key as a
    # cache key. This will result in a unique cache entry if any of these values
    # change.
    key = (hashlib.sha256(api_key.encode()).digest(), latitude, longitude, radius_m, limit)
    # READ FROM CACHE
    # With the cache lock, check if there is a matching entry that has not
    # expired. If a match is found, move the entry to the end and return a shallow
    # copy of the response with cached=True. Remove the matching expired value
    # before starting another search.
    with _cache_lock:
        cached = _cache.get(key)
        if cached and cached[0] > time.monotonic():
            _cache.move_to_end(key)
            return {**cached[1], "cached": True}
        _cache.pop(key, None)

    # INITIALIZE SEARCH TRACKING
    # selected will contain restaurants with photos. seen will be used to
    # track accepted place IDs so they are not re-accepted. pages_fetched will be
    # used to track how many pages have been parsed. candidates_fetched will be used to
    # track the number of raw features received from the provider. search_limited
    # will be used to track if a limit or an interrupted search has been set.
    selected, seen = [], set()
    pages_fetched = 0
    candidates_fetched = 0
    search_limited = False
    # PAGE AND DEADLINE BUDGET
    # Up to five pages with 100 candidates. One deadline can be used for all
    # photo enrichment. The offsets used will be zero, twenty, forty, sixty and
    # eighty. Twenty features are used per page. A shared deadline of sixty
    # seconds ahead of time can be passed to photo enrichment. Before making a
    # request to the provider check the remaining budget.
    deadline = time.monotonic() + 60
    try:
        for offset in range(0, 100, 20):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                search_limited = True
                break
            # GEOAPIFY PLACES REQUEST
            # Create a client using no redirects and a timeout that is eight seconds or
            # the remaining budget whichever is smaller. Search for catering.restaurant
            # within a circle with the center at longitude,latitude. Use proximity bias,
            # set twenty features per request and an offset. Prefer English.
            #
            # Close the client after the request using the context manager.
            with httpx.Client(timeout=min(8.0, remaining), follow_redirects=False) as client:
                response = client.get("https://api.geoapify.com/v2/places", params={
                    "categories": "catering.restaurant",
                    "filter": f"circle:{longitude},{latitude},{radius_m}",
                    "bias": f"proximity:{longitude},{latitude}",
                    "limit": 20,
                    "offset": offset,
                    "lang": "en",
                    "apiKey": api_key,
                })
            # AUTHENTICATION AND QUOTA HANDLING
            # Be specific in recognizing HTTP 401, 403 and 429 errors. If restaurants
            # with photos have already been selected keep those restaurants and set the
            # search limited as well as stop making more pages. Otherwise return
            # authentication_error or quota_reached immediately. Raise all other
            # unsuccessful HTTP responses to the error handler.
            if response.status_code in (401, 403, 429):
                if selected:
                    search_limited = True
                    break
                status = "quota_reached" if response.status_code == 429 else "authentication_error"
                return _response(status, "Geoapify could not complete the search. Check the backend API key and quota.", center, radius_m)
            response.raise_for_status()
            # VALIDATE PROVIDER RESPONSE
            # Parse the response as JSON and ensure that there is a features field that is
            # a list. Raise a value error if this is not the case. Increment pages_fetched
            # after receiving a valid features list and add the number of items in that list
            # to candidates_fetched. These include features that will later be filtered out.
            features = response.json().get("features")
            if not isinstance(features, list):
                raise ValueError("Unexpected provider payload")
            pages_fetched += 1
            candidates_fetched += len(features)
            restaurants = []
            # FILTER RESTAURANT FEATURES
            # Require a feature to have a dictionary for its properties and to have a
            # dictionary for its feature. Require a non-blank name string and a place_id
            # as a string that has not been seen previously. Convert restaurant
            # coordinates to floats and ensure that they are finite and within
            # geographic bounds. Skip restaurants that have invalid or missing
            # coordinates that have been handled.
            for feature in features:
                if not isinstance(feature, dict) or not isinstance(feature.get("properties"), dict):
                    continue
                properties = feature["properties"]
                name, place_id = properties.get("name"), properties.get("place_id")
                if not isinstance(name, str) or not name.strip() or not isinstance(place_id, str) or place_id in seen:
                    continue
                try:
                    restaurant_lat = float(properties["lat"])
                    restaurant_lon = float(properties["lon"])
                    if not (math.isfinite(restaurant_lat) and math.isfinite(restaurant_lon) and -90 <= restaurant_lat <= 90 and -180 <= restaurant_lon <= 180):
                        continue
                except (ValueError, TypeError, KeyError, OverflowError):
                    continue
                # READ SOURCE DATA
                # If datasource.raw is a dict use that. Otherwise use an empty dict.
                #
                # There are source fields that can contain translated names and website
                # data.
                source = properties.get("datasource")
                raw = source.get("raw") if isinstance(source, dict) else None
                raw = raw if isinstance(raw, dict) else {}
                # PRESERVE TRANSLATION OF NAMES
                # When matching images we want to preserve translated names while displaying
                # the original restaurant name. Geoapify may return an English name and a
                # Japanese name even when lang=en is requested. Store the original name,
                # address_line1, international names as well as the selected raw official,
                # English, Japanese, and alternate names. Store the original name as well as
                # all these other fields. Store only non-blank strings. Trim the strings and
                # deduplicate while maintaining order. Limit the number to eight.
                international = properties.get("name_international") or {}
                aliases = [name, properties.get("address_line1")]
                if isinstance(international, dict):
                    aliases.extend(international.values())
                aliases.extend(raw.get(key) for key in ("name:en", "name:ja", "official_name", "alt_name"))
                aliases = list(dict.fromkeys(value.strip() for value in aliases
                                            if isinstance(value, str) and value.strip()))[:8]
                # NORMALIZE RESTAURANT DATA
                # Set the place id of the accepted restaurant as seen and create a response
                # that
                # can be used by the frontend. Include fields for place id, original name,
                # alternate names, country, locality names, city, address, coordinates,
                # rounded straight-line distance and the validated website. Limit the
                # display
                # name to 200 characters and limit the address to 500 characters. Locality
                # names are used later for matching images through Wikimedia.
                seen.add(place_id)
                restaurants.append({
                    "id": place_id,
                    "name": name.strip()[:200],
                    "name_aliases": aliases,
                    "country": str(properties.get("country") or ""),
                    "location_names": [properties.get(field) for field in
                                       ("city", "state", "county", "suburb", "district", "quarter")
                                       if isinstance(properties.get(field), str)],
                    "city": str(properties.get("city") or ""),
                    "address": str(properties.get("formatted") or properties.get("address_line2") or "")[:500],
                    "latitude": restaurant_lat,
                    "longitude": restaurant_lon,
                    "distance_m": _distance_m(latitude, longitude, restaurant_lat, restaurant_lon),
                    "website": _website(properties.get("website") or raw.get("website") or raw.get("contact:website")),
                    # UNAVAILABLE PRICING AND REVIEWS
                    # Photos are from Commons. Menu prices and ratings are not provided by
                    # this
                    # connection. Do not make these up. Set image, image_source and rating
                    # to
                    # None. Menu pricing fields are not added by this service. Image fields
                    # can be
                    # populated later by photo enrichment.
                    "image": None,
                    "image_source": None,
                    # CUISINE AND OPENING HOURS
                    # If catering is a dictionary then use catering.cuisine first and then
                    # fall
                    # back to raw cuisine data. If catering is not a dictionary use an empty
                    # string for cuisine. Convert the cuisine field to text and limit it to
                    # 200 characters. Read opening_hours from either provider properties or
                    # from
                    # raw data. Convert the opening_hours data to text and limit it to 500
                    # characters. If opening_hours is missing use an empty string. These are
                    # provider properties and this function does not interpret the opening
                    # hours
                    # schedule or determine if the restaurant is currently open.
                    "cuisine": str(properties.get("catering", {}).get("cuisine") or raw.get("cuisine") or "")[:200] if isinstance(properties.get("catering", {}), dict) else "",
                    "opening_hours": str(properties.get("opening_hours") or raw.get("opening_hours") or "")[:500],
                    "rating": None,
                })
            # MATCH PHOTOS FOR EACH PAGE
            # Sort the restaurants from the current page that are valid by distance before
            # matching images. Call enrich_hotel_photos() with the number of remaining
            # image slots and the shared deadline. Only keep places with a truthy image
            # field. Add these places to selected and sort selected by distance and then
            # limit by the capped limit. These are the closest photo matches to restaurants
            # from the ones that were matched during the search. This function does not
            # check all restaurants in the area.
            restaurants.sort(key=lambda place: place["distance_m"])
            enriched = enrich_hotel_photos(restaurants, max_photos=limit-len(selected), deadline=deadline)
            selected.extend(place for place in enriched if place.get("image"))
            selected.sort(key=lambda place: place["distance_m"])
            selected = selected[:limit]
            # STOP WHEN ENOUGH RESTAURANTS MATCHED
            # Stop when selected has the requested capped limit of restaurants matched.
            #
            # If the deadline has been reached first set search limited and then stop.
            if len(selected) >= limit:
                break
            if time.monotonic() >= deadline:
                search_limited = True
                break
            # STOP AT END OF PROVIDER RESPONSES
            # A short page signifies the end of this search. Do not make empty pages.
            #
            # If there are less than twenty features on the page then stop paging.
            #
            # If the loop completes after checking all five offsets and does not break then
            # set search_limited=True because the number of candidate pages was exhausted.
            if len(features) < 20:
                break
        else:
            search_limited = True
        # BUILD A RESPONSE
        # Return status ok along with the restaurants that were selected.
        #
        # If no restaurants have matching photos explain that no photos were found
        # among the matching restaurants and suggest a larger radius.
        #
        # An empty result does not mean that there are no restaurants in the area.
        result = _response("ok", "" if selected else "No restaurants with matching photos found in the checked results. Try a larger search radius.", center, radius_m, selected)
    # IMPORT ERROR HANDLER
    # If an ImportError occurs while this function is being called return
    # configuration_error. Any imports that occur before this function is called
    # such as the top-level hotel_photos import will occur before this error handler can
    # catch the
    # import error.
    except ImportError:
        return _response("configuration_error", "Restaurant search could not start. Install backend-integration/requirements.txt and restart the backend.", center, radius_m)
    # TIMEOUT HANDLER
    # If a timeout occurs before any restaurants have been selected return
    # timeout while still allowing the landmark result to be used by the caller.
    # If restaurants have already been selected keep them. Set search limited and
    # return ok with a message about the remaining search timing out.
    except httpx.TimeoutException:
        if not selected:
            return _response("timeout", "Restaurant search took too long. Your landmark result is still available.", center, radius_m)
        search_limited = True
        result = _response("ok", "Some photo results are available; the remaining search timed out.", center, radius_m, selected)
    # PROVIDER ERROR HANDLER
    # Catch any of the listed HTTP, value, type and attribute errors. If no
    # selected restaurants are present return provider_error. Otherwise
    # preserve the selected restaurants, set search limited and return ok with a
    # message explaining that the remaining search could not be completed. Do not
    # include exception info or URL information in the message.
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        if not selected:
            return _response("provider_error", "Restaurants are temporarily unavailable. Please try again later.", center, radius_m)
        search_limited = True
        result = _response("ok", "Some photo results are available; the remaining search could not finish.", center, radius_m, selected)
    # SEARCH DIAGNOSTICS
    # Add pages_fetched, candidates_fetched and search_limited to completed or
    # partial results that are received by this function. Earlier error
    # responses will not include these additional diagnostic fields.
    result.update({"pages_fetched": pages_fetched, "candidates_fetched": candidates_fetched,
                   "search_limited": search_limited})

    # CACHE COMPLETED AND PARTIAL RESULTS
    # Only responses from successful provider searches including valid empty
    # responses are cached. More specifically responses that reach the response
    # caching step have a status of ok. These may also include partially completed
    # responses that were kept after a later failure from the provider.
    #
    # Limited searches are cached for sixty seconds while other completed searches
    # are cached for CACHE_SECONDS (normally ten minutes).
    #
    # Error responses that are returned immediately are not inserted into the cache.
    with _cache_lock:
        _cache[key] = (time.monotonic() + (60 if search_limited else CACHE_SECONDS), result)
        # BOUND THE CACHE AND RETURN
        # Insert under the cache lock and limit to a maximum of 256 items. Evict from
        # the oldest cache entry first while cache hits move entries to the end. Use
        # monotonic timestamps for expiration. The cache is lost on process
        # restarting. Return the response with cached=False if the search is new.
        while len(_cache) > 256:
            _cache.popitem(last=False)
    return result
