# SHARED GEOAPIFY HOTEL LOOKUP
# Shared hotel lookup with Geoapify via the Trip Canvas and image recognition.


# IMPORTS
# The hashlib module is used to use a different cache per API key. The math
# module is used to verify coordinates and calculate distance. The os module
# is used to read configuration and the threading module is used to protect
# cache access. The time module is used to handle monotonic deadlines and
# expiry. The OrderedDict module is used to maintain order of cache items.
# The Path class is used to locate the configuration file beside this module. The
# urlparse module is used to verify website links. The enrich_hotel_photos
# function is used to add images from Wikimedia Commons to places. The httpx
# module is used to make requests to the providers. The load_dotenv function
# is used to load the configuration for this module.
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
# The Geoapify credentials are kept away from the current admin/.env
# database so this is not changed. This module is read in from beside this
# module regardless of the current working directory. This file contains only
# GEOAPIFY_API_KEY. The .env.geoapify file that is next to this module is
# loaded with override=True. If values exist in this file they can override
# current environment variables for the same name.
load_dotenv(Path(__file__).resolve().with_name(".env.geoapify"), override=True)

# BACKEND ONLY DEFAULT KEY
# For this project there is a backend only default key. This can be overriden
# by environment variables. Do not copy this module or the key into
# frontend/src. The get_hotels() function will prefer to use a non-empty
# GEOAPIFY_API_KEY if present over using this key.
_DEFAULT_API_KEY = "040cccd2782d447997bd9eb36900b8fe"

# SHARED SEARCH CACHE
# This key is only used on the backend and is never sent to React. A cache
# is used so that on subsequent planner or upload visits there will not be
# another use of the API. Caches are stored in memory and reads and writes
# are protected by a lock. The default cache time is 600 seconds. Network
# requests are made outside of the lock so there is a chance of repeated
# processing if multiple cache misses occur.
_cache = OrderedDict()
_cache_lock = threading.Lock()
CACHE_SECONDS = 600


# STANDARD RESPONSE
# _response() returns status, message, hotels, center, radius, cache, provider,
# and attribution in a standard response format. If no list is provided an
# empty list of hotels will be used.
def _response(status, message, center=None, radius_m=5000, hotels=None, cached=False):
    return {
        "status": status,
        "message": message,
        "hotels": hotels if hotels is not None else [],
        "center": center,
        "radius_m": radius_m,
        "cached": cached,
        "provider": "Geoapify",
        "attribution": "Powered by Geoapify | © OpenStreetMap contributors",
    }


# VALIDATE WEBSITE LINKS
# Only return standard website links that can be safely opened by the user.
# Accept a string up to 2048 characters in length with a scheme of either
# HTTP or HTTPS, a hostname, and without a username or password. Return
# None for invalid values or values that are handled by URL parsing. This
# only validates that a URL is in a valid format and does not attempt to verify
# the contents of the website.
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


# STRAIGHT LINE DISTANCE
# This distance is straight line distance and not walking or driving distance.
# The _distance_m() function uses the haversine formula with an earth radius
# of 6371000 meters. The result of the haversine calculation is clamped to
# avoid rounding errors and then the distance is rounded and returned in
# meters.
def _distance_m(lat1, lon1, lat2, lon2):

    a, b = math.radians(lat1), math.radians(lat2)
    term = math.sin((b - a) / 2) ** 2
    term += math.cos(a) * math.cos(b) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return round(6371000 * 2 * math.asin(math.sqrt(min(1, max(0, term)))))


# HOTEL SEARCH ENTRY POINT
# Return hotel data or an unavailable response while maintaining recognition.
# For uploads, latitude and longitude are provided by Neon. For preset
# destinations and radius changes, the same service can be used through
# the endpoint GET /api/hotels. This module provides a service function and
# the endpoint is defined elsewhere.
def get_hotels(lat, lon, radius_m=5000, limit=3):





    # VALIDATE DESTINATION COORDINATES
    # Do not accept missing, empty, non-numeric, infinite, or out of range
    # coordinates. For valid coordinates convert to a float. Latitude must be
    # between -90 and 90 and longitude must be between -180 and 180. Return
    # missing_coordinates for handling of an invalid value.
    try:
        if lat is None or lon is None or lat == "" or lon == "":
            raise ValueError()
        latitude, longitude = float(lat), float(lon)
        if not (math.isfinite(latitude) and math.isfinite(longitude)):
            raise ValueError()
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError()
    except (ValueError, TypeError, OverflowError):
        return _response("missing_coordinates", "This landmark has no valid coordinates for hotel search.")
    # VALIDATE RADIUS AND LIMIT
    # radius_m and limit must be integers and cannot be a boolean. A radius from
    # 500 to 25000 meters is accepted and a limit from 1 to 20 is accepted.
    # Invalid inputs will return invalid_search.
    if type(radius_m) is not int or not 500 <= radius_m <= 25000 or type(limit) is not int or not 1 <= limit <= 20:
        return _response("invalid_search", "Use a radius of 500–25,000 meters and a limit of 1–20 hotels.")

    # LIMIT NUMBER OF HOTELS DISPLAYED
    # Up to three hotels with photos that match from the hotels that were
    # checked will be returned. The provided limit will be reduced to a maximum
    # of three after validation. A response center will be created using the
    # valid destination coordinates.
    limit = min(limit, 3)
    center = {"latitude": latitude, "longitude": longitude}
    # SELECT API KEY
    # Read the GEOAPIFY_API_KEY and strip leading and trailing whitespace. If
    # this does not provide a usable API key then fall back to the default key.
    # If neither provide a usable key then return not_configured. The API key is
    # not returned in a response provided to the frontend.
    api_key = os.getenv("GEOAPIFY_API_KEY", "").strip() or _DEFAULT_API_KEY
    if not api_key:
        return _response("not_configured", "Add GEOAPIFY_API_KEY to backend-integration/.env.geoapify and restart the backend.", center, radius_m)
    # IDENTITY FOR CACHE
    # Cache is keyed with a SHA256 digest of the API key, the exact latitude
    # and longitude coordinates, the radius and capped limit. Do not use the
    # API key as a key in the cache. This allows for different values of
    # coordinates and search parameters to have different cache keys.
    key = (hashlib.sha256(api_key.encode()).digest(), latitude, longitude, radius_m, limit)
    # READ FROM CACHE
    # When accessing the cache check for an existing cache item that has not
    # expired while holding the cache lock. If a cache item exists move it to the
    # end of the cache and return a shallow copy of a response with cached=True.
    # Remove an existing expired cache item before continuing with a new search.
    with _cache_lock:
        cached = _cache.get(key)
        if cached and cached[0] > time.monotonic():
            _cache.move_to_end(key)
            return {**cached[1], "cached": True}
        _cache.pop(key, None)

    # INITIALIZE SEARCH TRACKING
    # selected is a list of hotels with photos and seen is used to avoid duplicate
    # accepted place IDs. The number of pages parsed and the number of features
    # returned by the provider will also be tracked. search_limited will be set
    # to true if there is an imposed limit or if the search is interrupted and
    # this effects the number of hotels returned.
    selected, seen = [], set()
    pages_fetched = 0
    candidates_fetched = 0
    search_limited = False
    # PAGE AND DEADLINE BUDGET
    # Up to 5 pages / 100 candidates. One deadline is used for all batches of
    # photos. Offsets of zero, twenty, forty, sixty and eighty will be used with
    # twenty features per page. A shared deadline will be set sixty seconds in the
    # future and passed to the photo enrichment function. A check on the remaining
    # budget will be made prior to each request to the provider.
    # This uses a combination of deadlines and timeout instead of cancellation at
    # exactly sixty seconds based on elapsed time.
    deadline = time.monotonic() + 60
    try:
        for offset in range(0, 100, 20):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                search_limited = True
                break
            # GEOAPIFY PLACES REQUEST
            # Create an httpx client with no redirects and a timeout of min(8 seconds,
            # remaining budget). Make a request to search for accommodation.hotel within
            # a circle around the provided longitude,latitude. Use proximity bias, request
            # twenty features with an offset and prefer English language. Close the client
            # using the context manager after the request.
            with httpx.Client(timeout=min(8.0, remaining), follow_redirects=False) as client:
                response = client.get("https://api.geoapify.com/v2/places", params={
                    "categories": "accommodation.hotel",
                    "filter": f"circle:{longitude},{latitude},{radius_m}",
                    "bias": f"proximity:{longitude},{latitude}",
                    "limit": 20,
                    "offset": offset,
                    "lang": "en",
                    "apiKey": api_key,
                })
            # AUTHENTICATION AND QUOTA HANDLING
            # Recognize HTTP 401, 403 and 429. If hotels with photos have already been
            # selected then keep them, mark the search as limited and stop fetching more
            # pages. For all other cases return either authentication_error or
            # quota_reached immediately. Any other failure in the HTTP response will be
            # passed to the general error handler.
            if response.status_code in (401, 403, 429):
                if selected:
                    search_limited = True
                    break
                status = "quota_reached" if response.status_code == 429 else "authentication_error"
                return _response(status, "Geoapify could not complete the search. Check the backend API key and quota.", center, radius_m)
            response.raise_for_status()
            # VALIDATE PROVIDER RESPONSE
            # Parse the response as JSON and require a features array. If the response
            # does not have a features array then raise a value error. Increment
            # pages_fetched after receiving a response with a features array and add the
            # length of this array to candidates_fetched. These counters include all of the
            # features received whether or not they are later filtered.
            features = response.json().get("features")
            if not isinstance(features, list):
                raise ValueError("Unexpected provider payload")
            pages_fetched += 1
            candidates_fetched += len(features)
            hotels = []
            # FILTER HOTEL FEATURES
            # Features must be a dictionary and properties must be a dictionary. The name
            # property must be a non-empty string and place_id must be a string that has
            # not already been seen. Convert hotel coordinates to floats and verify they
            # are finite and within the geographic bounds. Do not consider candidates with
            # missing or invalid coordinates that have already been handled.
            for feature in features:
                if not isinstance(feature, dict) or not isinstance(feature.get("properties"), dict):
                    continue
                properties = feature["properties"]
                name, place_id = properties.get("name"), properties.get("place_id")
                if not isinstance(name, str) or not name.strip() or not isinstance(place_id, str) or place_id in seen:
                    continue
                try:
                    hotel_lat = float(properties["lat"])
                    hotel_lon = float(properties["lon"])
                    if not (math.isfinite(hotel_lat) and math.isfinite(hotel_lon) and -90 <= hotel_lat <= 90 and -180 <= hotel_lon <= 180):
                        continue
                except (ValueError, TypeError, KeyError, OverflowError):
                    continue
                # READ FROM SOURCE
                # When the datasource.raw value is a dictionary then use this dictionary
                # otherwise use an empty dictionary. The source data can provide translated
                # names and website information.
                source = properties.get("datasource")
                raw = source.get("raw") if isinstance(source, dict) else None
                raw = raw if isinstance(raw, dict) else {}
                # PRESERVE TRANSLATED NAMES
                # When matching images, translated names should be preserved while the
                # hotel’s name should not be changed. Geoapify can provide both an English
                # hotel name and a Japanese hotel name even when the lang parameter is set
                # to en. Store the original name, address_line1, international names and the
                # selected raw English, Japanese, official, and alternate names. Store the
                # original name, address_line1, international names and the selected raw
                # English, Japanese, official, and alternate names. Store non-empty strings,
                # trim them, deduplicate and maintain the order. Only store up to eight
                # strings.
                international = properties.get("name_international") or {}
                aliases = [name, properties.get("address_line1")]
                if isinstance(international, dict):
                    aliases.extend(international.values())
                aliases.extend(raw.get(key) for key in ("name:en", "name:ja", "official_name", "alt_name"))
                aliases = list(dict.fromkeys(value.strip() for value in aliases
                                            if isinstance(value, str) and value.strip()))[:8]
                # NORMALIZE HOTEL DATA
                # Mark the accepted place ID as seen and create a hotel object with the
                # following properties: ID, original name, aliases, country, locality names,
                # city, address, coordinates, straight line distance, and the validated
                # website link.
                # The display name should not be more than 200 characters in length and the
                # address should not be more than 500 characters in length. Locality names
                # can be used to match images from Wikimedia Commons later.
                seen.add(place_id)
                hotels.append({
                    "id": place_id,
                    "name": name.strip()[:200],
                    "name_aliases": aliases,
                    "country": str(properties.get("country") or ""),
                    "location_names": [properties.get(field) for field in
                                       ("city", "state", "county", "suburb", "district", "quarter")
                                       if isinstance(properties.get(field), str)],
                    "city": str(properties.get("city") or ""),
                    "address": str(properties.get("formatted") or properties.get("address_line2") or "")[:500],
                    "latitude": hotel_lat,
                    "longitude": hotel_lon,
                    "distance_m": _distance_m(latitude, longitude, hotel_lat, hotel_lon),
                    "website": _website(properties.get("website") or raw.get("website") or raw.get("contact:website")),
                    # UNAVAILABLE PRICING AND REVIEWS
                    # This integration with the Geoapify Places API does not provide room
                    # pricing, availability or reviews. Photos are matched separately from
                    # Commons.
                    # image, image_source, nightly_price and rating are all set to None. Do
                    # not
                    # create images, ratings or prices when not provided by the provider.
                    "image": None,
                    "image_source": None,
                    "nightly_price": None,
                    "rating": None,
                })
            # MATCH PHOTOS FOR EACH PAGE
            # Sort the valid hotels for the current page by distance and then use
            # enrich_hotel_photos() with the number of remaining hotels with photos to
            # match and the shared deadline. Only keep hotels with a truthy image property.
            # Combine these hotels into selected, sort selected by distance and limit the
            # number to the capped limit. These are the closest matching hotels with photos
            # from among the hotels that have been checked. The search does not attempt to
            # match photos to all hotels in the area.
            hotels.sort(key=lambda place: place["distance_m"])
            enriched = enrich_hotel_photos(hotels, max_photos=limit-len(selected), deadline=deadline)
            selected.extend(place for place in enriched if place.get("image"))
            selected.sort(key=lambda place: place["distance_m"])
            selected = selected[:limit]
            # STOP WHEN ENOUGH HOTELS ARE FOUND
            # Stop fetching hotels when the number of selected hotels reaches the
            # requested capped limit. If the deadline is reached before the number of
            # selected hotels reaches the requested limit then mark the search as limited
            # and stop fetching.
            if len(selected) >= limit:
                break
            if time.monotonic() >= deadline:
                search_limited = True
                break
            # STOP AT END OF PROVIDER RESULTS
            # A short page marks the end of this search. Do not try to fetch empty
            # pages. If there are less than twenty features in a page stop paging. If the
            # loop does not break after having iterated over all five offsets then set
            # search_limited to true as the limit on candidate pages was reached.
            if len(features) < 20:
                break
        else:
            search_limited = True
        # BUILD RESPONSE FOR COMPLETE SEARCH
        # Return status ok and the selected hotels. If no hotels have matching photos
        # then explain that there were not matching photos found from the hotels that
        # were checked and suggest increasing the radius. This does not mean that there
        # are no hotels in the area.
        result = _response("ok", "" if selected else "No hotels with matching photos found in the checked results. Try a larger search radius.", center, radius_m, selected)
    # IMPORT ERROR HANDLER
    # If an ImportError occurs and this error handler is reached then return
    # configuration_error. Imports that occur at the time a module is loaded such
    # as the import of hotel_photos at the top level occur before this
    # error handler can catch them.
    except ImportError:
        return _response("configuration_error", "Hotel search could not start. Install backend-integration/requirements.txt and restart the backend.", center, radius_m)
    # TIMEOUT HANDLER
    # If a timeout occurs and there are no selected hotels then return timeout,
    # keeping the landmark result available to the caller. If there are already
    # selected hotels keep them and mark the search as limited and return ok with
    # a message that the remaining search timed out.
    except httpx.TimeoutException:
        if not selected:
            return _response("timeout", "Hotel search took too long. Your landmark result is still available.", center, radius_m)
        search_limited = True
        result = _response("ok", "Some photo results are available; the remaining search timed out.", center, radius_m, selected)
    # PROVIDER ERROR HANDLER
    # Catch any of the listed errors: HTTP, value, type or attribute. If there are
    # no selected hotels then return provider_error. Otherwise keep the selected
    # hotels and mark the search as limited and return ok with a message that the
    # remaining search could not complete. Do not include exception details or
    # request URLs in the message.
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        if not selected:
            return _response("provider_error", "Hotels are temporarily unavailable. Please try again later.", center, radius_m)
        search_limited = True
        result = _response("ok", "Some photo results are available; the remaining search could not finish.", center, radius_m, selected)
    # SEARCH DIAGNOSTICS
    # For complete or partial responses that reach this point add the number
    # of pages fetched, number of candidates fetched and whether the search was
    # limited to the response. Earlier responses that return an error do not have
    # this information added.
    result.update({"pages_fetched": pages_fetched, "candidates_fetched": candidates_fetched,
                   "search_limited": search_limited})

    # CACHE COMPLETE AND PARTIAL RESPONSES
    # Only responses from the provider that are successful including valid
    # empty responses will be cached. More specifically only responses that have
    # reached the point at which a response is cached will have status ok. These
    # responses can include partial results that were retained following a later
    # failure of the provider. Limited searches will be cached for 60 seconds and
    # all other complete searches will be cached for CACHE_SECONDS (normally 10
    # minutes). Immediate error responses will not be cached here as they will be
    # returned before reaching this point.
    with _cache_lock:
        _cache[key] = (time.monotonic() + (60 if search_limited else CACHE_SECONDS), result)
        # BOUND CACHE AND RETURN
        # Insert under the cache lock and limit to 256 entries. When the limit is exceeded
        # after insertion the
        # oldest cache entry based on order will be removed first.
        # Cache hits will move the cache entry to the end. Expire using monotonic
        # time. The cache is lost on process restart. Return the response with
        # cached=False if a new search is being performed.
        while len(_cache) > 256:
            _cache.popitem(last=False)
    return result
