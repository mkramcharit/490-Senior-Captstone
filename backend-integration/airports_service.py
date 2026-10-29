# NEAREST MAPPED AIRPORT LOOKUP
# Uses existing backend Geoapify API key to return the nearest mapped airport


# IMPORTS
# hashlib is used to generate a hash of the API key so that cached results
# can be separated by API key
# math is used to determine if provided coordinates are finite
# os is used to load configuration data
# re is used to match airport codes
# threading is used to protect caching of shared data
# time is used to provide monotonic timestamps for cache expiration
# OrderedDict is used to maintain the order of cached results to enable
# least-recently-used eviction
# httpx is used to make requests to the Geoapify API
# Instead of implementing the functionality to calculate distance
# and provide a website lookup, we reuse the functions implemented
# in the hotels_service functionality and use the default API key.
import hashlib
import math
import os
import re
import threading
import time
from collections import OrderedDict

import httpx
from hotels_service import _DEFAULT_API_KEY, _distance_m, _website

# SHARED CACHE
# Airport lookup results are stored in this process's memory.
# When a request is made to read or update the cache a lock is acquired
# to ensure only one thread can read or update the cache at a time.
# The lock does not cover the request to the provider so multiple
# cache misses can cause multiple requests to the provider.
_cache = OrderedDict()
_cache_lock = threading.Lock()


# STANDARD RESPONSE
# _response() provides a standard response with status, message, airport,
# cached, provider and attribution fields.
# New responses are created with cached=False and identify Geoapify
# and OpenStreetMap.
# If no airport data is found the airport value will be None.
def _response(status, message="", airport=None):
    return {"status": status, "message": message, "airport": airport,
            "cached": False, "provider": "Geoapify",
            "attribution": "Powered by Geoapify | © OpenStreetMap contributors"}


# VALIDATE AIRPORT CODES
# _code() takes an input of a string consisting of the number of ASCII
# letters requested. If the code matches then the code will be
# returned in uppercase format or None if the code does not match.
# IATA codes use three characters and ICAO codes use four.
# This does not confirm that the code has been assigned to an airport.
# Only the format of the code is confirmed.
def _code(value, length):
    return value.upper() if isinstance(value, str) and re.fullmatch(r"[A-Za-z]{%d}" % length, value) else None


# AIRPORT SEARCH
# Use proximity matching without a hotel-based radius that excludes airports.
#
# Airports are mapped facilities not guaranteed for scheduled passenger
# service. Distances returned are straight-line and based on facility
# coordinates.
# The airport category is searched by default or the international airport
# category if international_only is True, with up to 20 features returned.
# The nearest valid airport from the list of airports returned by the
# provider will be returned. This does not guarantee that the nearest
# airport from all airports in the world will be returned.
def get_nearest_airport(lat, lon, international_only=False):
    
    # VALIDATE DESTINATION COORDINATES
    # Reject missing coordinates, empty strings, non-numeric data, infinite
    # values and coordinates that lie outside the valid latitude and longitude
    # ranges. Latitude ranges from -90 to +90 and longitude ranges from
    # -180 to +180.
    # The missing_coordinates status will be returned with a meaningful error message
    # for invalid inputs.
    try:
        if lat is None or lon is None or lat == "" or lon == "":
            raise ValueError()
        latitude, longitude = float(lat), float(lon)
        if not (math.isfinite(latitude) and math.isfinite(longitude) and
                -90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError()
    except (ValueError, TypeError, OverflowError):
        return _response("missing_coordinates", "This landmark needs valid coordinates to find its closest airport.")
    # VALIDATE SEARCH OPTION
    # international_only must be a Python boolean instead of a number or string.
    # Return invalid_search if international_only is of the wrong type.
    if type(international_only) is not bool:
        return _response("invalid_search", "Choose all airports or international airports only.")
    # SELECT BACKEND API KEY
    # If the value of GEOAPIFY_API_KEY has any content other than whitespace
    # then use the value of GEOAPIFY_API_KEY. Otherwise use _DEFAULT_API_KEY
    # from hotels_service. If neither of these provides a value that can be used
    # return not_configured.
    # Since the API key is used in the backend the key does not need to be sent to
    # the frontend.
    api_key = os.getenv("GEOAPIFY_API_KEY", "").strip() or _DEFAULT_API_KEY
    if not api_key:
        return _response("not_configured", "Configure the existing Geoapify API key on the backend.")
    # CACHE ID
    # Create a cache key using the SHA256 hash of the API key, the latitude
    # and longitude values (as floats), and the value of international_only.
    # This allows different API keys, different coordinates, and different
    # search types to be separated without saving the actual value of the API
    # key as the value in the cache dictionary.
    # The coordinates are not rounded so slightly different coordinates will have
    # different cache keys.
    key = (hashlib.sha256(api_key.encode()).digest(), latitude, longitude, international_only)
    # READ CACHE
    # Obtain a lock on the cache and check if a cache value exists and is not expired.
    # If such a value exists move the value to the end of the cache to indicate
    # that it is recently used. Return a copy of the response object with
    # cached=True without modifying the original response object.
    # Remove expired items from the cache before requesting a response from a
    # provider.
    with _cache_lock:
        cached = _cache.get(key)
        if cached and cached[0] > time.monotonic():
            _cache.move_to_end(key)
            return {**cached[1], "cached": True}
        _cache.pop(key, None)
    try:
        # HTTP CLIENT
        # Create an HTTP client with an 8 second timeout.
        # Do not follow redirects.
        # After the request to the provider close the client using the context manager.
        with httpx.Client(timeout=8.0, follow_redirects=False) as client:
            # GEOAPIFY PLACES REQUEST
            # Request airport type (or airport.international if international_only is set).
            # Set a bias based on the destination using longitude,latitude.
            # Request up to 20 features and prefer English results.
            # No radius is specified so the search is not constrained to the radius used
            # for nearby hotels and restaurants.
            # The international airport type matches the provider's mapping and does not
            # indicate any guaranteed scheduled flights or flights for a particular route.
            response = client.get("https://api.geoapify.com/v2/places", params={
                "categories": "airport.international" if international_only else "airport",
                "bias": f"proximity:{longitude},{latitude}",
                "limit": 20, "lang": "en", "apiKey": api_key,
            })
        # AUTHORIZATION AND QUOTA ERROR HANDLING
        # Return authentication_error for status codes of 401 or 403 with message
        # of backend-key.
        # Return quota_reached for status codes of 429 and ask the user to try later.
        # For all other failures in the HTTP request pass the exception to the
        # shared handler.
        if response.status_code in (401, 403):
            return _response("authentication_error", "Geoapify could not authorize the airport search. Check the backend key.")
        if response.status_code == 429:
            return _response("quota_reached", "Geoapify's request limit has been reached. Try again later.")
        response.raise_for_status()
        # VALIDATE PROVIDER RESPONSE
        # Decode the response and check that the response has a features field
        # that is a list. If the response has an unexpected format return
        # provider_error.
        # Create an empty list of candidates and a set of accepted place IDs.
        features = response.json().get("features")
        if not isinstance(features, list):
            raise ValueError("Unexpected airport response")
        airports, seen = [], set()
        # READ EACH FEATURE
        # Skip features that are not objects or that do not have the required
        # properties of an object.
        # A name must be present and non blank and a place_id must be present as
        # a string.
        # Skip a place ID if it is already in the accepted set to avoid having
        # duplicate airport candidates.
        for feature in features:
            properties = feature.get("properties") if isinstance(feature, dict) else None
            if not isinstance(properties, dict):
                continue
            name, place_id = properties.get("name"), properties.get("place_id")
            if not isinstance(name, str) or not name.strip() or not isinstance(place_id, str) or place_id in seen:
                continue
            # READ SOURCE DATA
            # If datasource.raw is an object use that data, otherwise use an empty
            # object.
            # Combine the main name with the raw English name and use a case insensitive
            # match for matching names.
            # Source data can contain airport codes, airport names in other languages,
            # websites, and tags for airports.
            source = properties.get("datasource")
            raw = source.get("raw") if isinstance(source, dict) else None
            raw = raw if isinstance(raw, dict) else {}
            names = " ".join(value for value in (name, raw.get("name:en")) if isinstance(value, str)).casefold()
            # FILTER HELIPADS BY NAME
            # Some heliports are only tagged as aerodromes. The translated name
            # can be used to more accurately identify heliports such as Tokyo Heliport.
            # Do not accept heliport, helipad or the Japanese ヘリポート in the name.
            # This is a name-based filter and does not represent a complete solution to
            # determining heliports in all languages or in all types of facilities.
            if "heliport" in names or "helipad" in names or "ヘリポート" in names:
                continue
            # FILTER NON-AIRPORT FACILITIES
            # Helipads and terminals are not airports themselves.
            # Skip features where the raw aeroway property is helipad, heliport,
            # terminal or gate. This will prevent helipads and terminals from being
            # returned as airports.
            if raw.get("aeroway") in ("helipad", "heliport", "terminal", "gate"):
                continue
            # VALIDATE AIRPORT COORDINATES
            # Obtain the lat and lon from the provider and convert the values to floats.
            # The values must be finite and within the valid ranges for latitude
            # and longitude.
            # Skip a candidate if the coordinates are missing, malformed or out of
            # range. After passing these validations mark the place_id as seen.
            try:
                airport_lat, airport_lon = float(properties["lat"]), float(properties["lon"])
                if not (math.isfinite(airport_lat) and math.isfinite(airport_lon) and
                        -90 <= airport_lat <= 90 and -180 <= airport_lon <= 180):
                    continue
            except (ValueError, TypeError, OverflowError, KeyError):
                continue
            seen.add(place_id)
            # EXTRACT AIRPORT NAME AND CODES
            # Obtain airport specific properties if available.
            # If a name_international.en property exists use this for an English name.
            # Otherwise use the raw name:en property if the first value is not present
            # or falsey.
            # Keep the original named value.
            # Limit both the English name and the original name to 200 characters.
            info = properties.get("airport")
            info = info if isinstance(info, dict) else {}
            international_names = properties.get("name_international")
            english = international_names.get("en") if isinstance(international_names, dict) else None
            english = english or raw.get("name:en")
            # NORMALIZE AIRPORT RETURN VALUE
            # Return the place ID, names, IATA and ICAO codes, address, coordinates,
            # straight-line distance in meters and website.
            # Limit the address string to 500 characters.
            # First obtain code values from airport properties and then from source data.
            # Obtain a website from either a property or the raw website field and
            # pass the value through the shared website helper.
            # Use the _distance_m function to calculate distance based on the destination
            # and facility coordinates.
            airports.append({
                "id": place_id, "name": name.strip()[:200],
                "english_name": english[:200] if isinstance(english, str) else None,
                "iata": _code(info.get("iata") or raw.get("iata"), 3),
                "icao": _code(info.get("icao") or raw.get("icao"), 4),
                "address": str(properties.get("formatted") or "")[:500],
                "latitude": airport_lat, "longitude": airport_lon,
                "distance_m": _distance_m(latitude, longitude, airport_lat, airport_lon),
                "website": _website(properties.get("website") or raw.get("website") or raw.get("contact:website")),
            })
        # SELECT CLOSEST RETURNED CANDIDATE
        # Sort accepted airports by distance_m in ascending order.
        # Return the first airport if there is at least one accepted airport.
        # If there are no accepted airports return a status of ok with
        # airport=None and no-matching-airport as a message.
        # Add international_only to this search response.
        airports.sort(key=lambda airport: airport["distance_m"])
        result = _response("ok", "" if airports else "No matching airport was returned for this landmark.", airports[0] if airports else None)
        result["international_only"] = international_only
    # TIMEOUT HANDLING
    # If a timeout occurs in the HTTP request return timeout with a meaningful
    # error message.
    # The failure to find an airport does not affect the trip itself.
    # This error response is returned before cache insertion.
    except httpx.TimeoutException:
        return _response("timeout", "The airport search timed out. Your trip is still available.")
    # HANDLING OF PROVIDER ERRORS
    # Exceptions may contain the API key in a URL. Do not expose the key.
    # Handle HTTP, type, attribute, and parsing errors and return a generic
    # provider_error response. Do not return the exception text in the response.
    # Authentication errors, quota errors, timeout errors, and provider errors
    # are not cached by this function because these responses are handled by handlers
    # that execute before cache insertion.
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        return _response("provider_error", "The airport search is temporarily unavailable.")
    # CACHE COMPLETE SEARCHES
    # Cache a complete search for 86400 seconds (24 hours). Use monotonic
    # time to ensure the expiration is not affected by changes in the system clock.
    # Cache both a search with a matching airport and a search with no matching
    # airport.
    # Keep a maximum of 256 results and remove the least recently used item first.
    # When a cache hit occurs move an item to the end of the cache to implement
    # least-recently-used eviction.
    # The cache is only local to this process and will be lost on process restart.
    with _cache_lock:
        _cache[key] = (time.monotonic() + 86400, result)
        while len(_cache) > 256:
            _cache.popitem(last=False)
    # RETURN THE RESULT
    # Return the response with cached=False if a new search is completed.
    # If a cache hit occurs then return the same search information with
    # cached=True.
    return result
