# RESOLVED FEATURED DESTINATIONS
#
# Resolves curated entry points to physical locations at Neon. Does not resolve to arbitrary
# IDs.
#
# These functions are provided with search and lookup functions from the database.
#
# The preset config uses a location and search strings rather than hardcoded IDs to database
# locations.

# IMPORTS
#
# inspect is used to get the parameters that the nearby-landmark function takes
#
# math is used to validate coordinates
#
# re is used to normalize names so they can match
#
# threading is used to allow shared access to cache
#
# time can be used to determine when cache entries have expired
#
# OrderedDict can be used to keep a list of locations in a least-recently used fashion in
# cache
import inspect
import math
import re
import threading
import time
from collections import OrderedDict

# CURATED PRESETS
#
# When planning routes, a broad travel card will be anchored to a location. A card will be
# linked to a location before a route is planned.
#
# PRESETS maps a front-end preset ID to a list of search aliases for a location and a
# location that defines the region of interest.
#
# For example, the preset for amazon will search for the Amazon Theatre in Manaus and the
# orlando preset will search for Cinderella Castle and aliases of that name.
#
# The search locations used are for validation but will ultimately use the location IDs
# provided by the location database.
PRESETS = {
    'orlando': {'queries': ['Cinderella_Castle', 'Magic_Kingdom', 'Walt_Disney_World'], 'center': (28.42, -81.58)},
    'tokyo': {'queries': ['Tokyo_Tower'], 'center': (35.66, 139.75)},
    'paris': {'queries': ['Eiffel_Tower'], 'center': (48.86, 2.29)},
    'amazon': {'queries': ['Amazon_Theatre', 'Teatro_Amazonas', 'Amazonas_Theatre'], 'center': (-3.13, -60.02)},
    'rio': {'queries': ['Christ_the_Redeemer', 'Cristo_Redentor'], 'center': (-22.95, -43.21)},
    'new-york': {'queries': ['Statue_of_Liberty', 'Liberty_Enlightening_the_World'], 'center': (40.69, -74.04)},
    'great-wall': {'queries': ['Mutianyu', 'Great_Wall_of_China', 'Great_Wall'], 'center': (40.43, 116.57)},
    'amalfi': {'queries': ['Amalfi_Cathedral', 'Duomo_di_Amalfi', 'Cathedral_of_Amalfi'], 'center': (40.63, 14.60)},
}
# SHARED CACHE AND LOCK
#
# This module will keep any resolved featured destinations in memory within the process.
#
# A lock is used to access the cache for reading or writing.
#
# Database lookups and payload construction are not protected by the lock so the same work
# could be done more than once for concurrent callers when missing a preset.
_cache = OrderedDict()
_lock = threading.Lock()


# FEATURED DESTINATION EXCEPTION
#
# FeaturedUnavailable is a subclass of ValueError that is used to indicate a missing preset
# or a preset that cannot be matched to a database location.
#
# The consumer of this module can then convert this exception to a user-facing message or an
# HTTP response.
class FeaturedUnavailable(ValueError):
    pass


# NORMALIZE MATCHING NAMES
#
# words() converts to string and strips out any falsey values. Underscores are converted to
# spaces and leading Category: is stripped out.
#
# Consecutive non-word characters are replaced with spaces.
#
# casefold() is used and whitespace is stripped out.
#
# The regular expression used maintains Unicode word characters.
#
# The stripping out of Category: happens before casefolding and is case-sensitive.
#
# This function does not do Unicode normalization or accent stripping.
def words(value):
    return re.sub(r'[^\w]+', ' ', str(value or '').replace('_', ' ').removeprefix('Category:'), flags=re.UNICODE).casefold().strip()


# VALIDATE THE PRESET
#
# choose_landmark() will retrieve the preset specified
#
# If the preset_id is not a defined preset, FeaturedUnavailable is raised
#
# A dictionary of candidate scores will be initialized. Aliases provided in the preset will
# be normalized for matching.
def choose_landmark(preset_id, search, lookup):
    config = PRESETS.get(preset_id)
    if not config:
        raise FeaturedUnavailable('This featured destination is not available.')
    candidates = {}
    queries = [words(query) for query in config['queries']]
    # SEARCH FOR DATABASE LOCATIONS
    #
    # Each alias in the preset will be searched for in its original form using the search
    # function once.
    #
    # If the search result is falsey then it will be treated as empty.
    #
    # Only rows that are dictionaries and have a non-None landmark_id will be processed.
    #
    # Name and category_name will be normalized before the row is scored
    for query in config['queries']:
        for row in search(query) or []:
            if not isinstance(row, dict) or row.get('landmark_id') is None:
                continue
            name, category = words(row.get('name')), words(row.get('category_name'))
            # RANK NAME AND CATEGORY MATCHES
            #
            # First name will be matched exactly, then category will be matched if not exact
            # name. Do not select a nearby landmark just to fill out a card.
            #
            # For each alias provided, a name match will score 100 points, an exact category
            # match will score 90 points, a substring in a name will score 50 points and a
            # substring in a category will score 30 points.
            #
            # The position of each alias will be subtracted from the score to reward earlier
            # listed aliases.
            #
            # The highest score will be stored for the row and must be positive.
            #
            # Substring matches do not require a complete word match.
            score = max((100 if name == q else 90 if category == q else 50 if q in name else 30 if q in category else 0) - i
                        for i, q in enumerate(queries))
            # DEDUPLICATE CANDIDATES
            #
            # Each landmark_id that is accepted will be converted to an integer and the
            # highest score for that landmark_id will be kept.
            #
            # Multiple search results for the same landmark will result in just one
            # candidate.
            #
            # Malformed IDs may cause an exception during this process. This conversion is
            # not done in the coordinate validation function later in the process.
            if score > 0:
                identity = int(row['landmark_id'])
                candidates[identity] = max(candidates.get(identity, 0), score)
    possible = []
    anchor_lat, anchor_lon = config['center']
    # LIMIT DATABASE LOOKUPS
    #
    # Candidates will be sorted in descending order of score and then by ascending
    # landmark_id.
    #
    # The first twelve candidates in this order will be looked up completely in the
    # database.
    #
    # Candidates will be skipped if lookup() returns a falsey value.
    #
    # If all the checked results fail the geolocation check then further lower ranked
    # candidates will not be attempted.
    for identity, rank in sorted(candidates.items(), key=lambda item: (-item[1], item[0]))[:12]:
        row = lookup(identity)
        if not row:
            continue
        try:
            # VALIDATE DATABASE COORDINATES
            #
            # lat and lon values in a database result will be converted to floats.
            #
            # Values must be finite in latitude from -90 to 90 and in longitude from -180 to
            # 180.
            #
            # Rows that fail the type, value, or missing a key checks will be skipped.
            lat, lon = float(row['lat']), float(row['lon'])
            if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            # MATCH THE INTENDED LOCATION
            #
            # Match the intended location (e.g. Tokyo Tower in Japan) instead of an
            # unrelated location with the same displayed name in a different country.
            #
            # The date line will be used to find the smallest longitude difference.
            #
            # Locations that are more than 2 degrees in latitude or longitude away from the
            # intended location will be rejected.
            #
            # This is a geolocation check in degrees and not a fixed distance in kilometers.
            delta_lon = abs((lon - anchor_lon + 180) % 360 - 180)
            if abs(lat - anchor_lat) > 2 or delta_lon > 2:
                continue
            # CHOOSE THE BEST VALID LOCATION
            #
            # For valid candidates, negative rank, squared angular distance from the anchor
            # point, landmark ID, and a reference to the database row will be stored.
            #
            # These values will be sorted first by best rank then by angular distance and
            # then by landmark ID.
            #
            # The best rank database row will be returned.
            #
            # If no valid candidates remain then FeaturedUnavailable will be raised instead
            # of inventing a new location or replacing a valid location with an unrelated
            # location.
            possible.append((-rank, (lat-anchor_lat)**2 + delta_lon**2, identity, row))
        except (ValueError, TypeError, KeyError):
            continue
    if not possible:
        raise FeaturedUnavailable('This featured landmark could not be matched to a location in the landmark database. Please try another destination.')
    possible.sort(key=lambda candidate: candidate[:3])
    return possible[0][3]


# BUILD THE FRONTEND PAYLOAD
#
# destination_payload() takes a database row and converts to the payload used by the
# frontend.
#
# landmark_id will be stored as an integer
#
# First the displayed name is used, otherwise category_name will be cleaned (Category:
# stripped out and underscores replaced by spaces) and then finally the label Featured
# landmark will be used.
#
# Name comparisons use truthiness and do not strip out whitespace-only names.
def destination_payload(row, preset_id, photos, nearby):
    identity = int(row['landmark_id'])
    name = row.get('name') or str(row.get('category_name') or '').replace('Category:', '').replace('_', ' ') or 'Featured landmark'
    # LOAD LANDMARK PHOTOS
    #
    # Up to five photos will be requested with the landmark_id and limit keyword arguments.
    #
    # Only photos with a URL containing non-whitespace characters will be kept
    #
    # If the row has a truthy url, it will be used as the primary photo, otherwise the first
    # photo provided or None will be used. No URL scheme or host validation is done.
    #
    # Errors in getting photos are outside the optional-nearby function and will be
    # propagated.
    urls = [url for url in photos(landmark_id=identity, limit=5) if isinstance(url, str) and url.strip()]
    image = row.get('url') or (urls[0] if urls else None)
    # USE DATABASE LOCATION DATA
    #
    # lat and lon will be read from the selected row and converted to floats and passed
    # through to the response and to the nearby lookup
    #
    # These locations have already been verified by the caller in the choose_landmark()
    # function.
    lat, lon = float(row['lat']), float(row['lon'])
    neighbors = []
    try:
        # PREPARE OPTIONAL NEARBY LOOKUP
        #
        # Latitude, longitude, the landmark ID, an exclusion ID, a limit of four and a
        # distance of 600 kilometers will be prepared for the nearby function.
        #
        # These parameters are requested but which ones are passed depends on the signature
        # of the nearby function. Filtering is done based on how the nearby function works.
        options = {'lat': lat, 'lon': lon, 'landmark_id': identity, 'exclude_landmark_id': identity,
                   'limit': 4, 'max_distance_km': 600.0}
        # ADAPT TO THE NEARBY FUNCTION SIGNATURE
        #
        # The nearby function will be examined before being called.
        #
        # If the nearby function supports arbitrary keyword arguments then all of the
        # prepared values will be passed
        #
        # If the nearby function does not support arbitrary keyword arguments then only the
        # values that are in the function signature will be passed
        #
        # Using signature.bind() it can be determined if the keyword arguments passed can be
        # used to form a valid call to the function before making the function call. The
        # function will not be called again after a failure.
        signature = inspect.signature(nearby)
        kwargs = options if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values()) else {key: value for key, value in options.items() if key in signature.parameters}
        signature.bind(**kwargs)
        # FORMAT NEARBY LOCATIONS
        #
        # Rows returned from the nearby function will be converted into objects with the
        # properties ID, display name, city, state, country, latitude, longitude, image and
        # distance in kilometers.
        #
        # The displayed name will be preferred then the category of the nearby location will
        # be cleaned.
        #
        # None of the following are performed separately: removing the selected landmark,
        # enforcing a 600 km max distance, or limiting the number of locations returned
        # after processing by the nearby function.
        for item in nearby(**kwargs) or []:
            neighbors.append({'id': item['landmark_id'], 'name': item.get('name') or str(item.get('category_name') or '').replace('Category:', '').replace('_', ' '),
                'city': item.get('city'), 'state': item.get('state'), 'country': item.get('country'),
                'latitude': item.get('lat'), 'longitude': item.get('lon'), 'image': item.get('url'),
                'distance_km': item.get('distance_km')})
    # ISOLATE OPTIONAL NEARBY FAILURES
    #
    # Optional nearby locations should not hide a valid featured location.
    #
    # If any of the following happen: examining the function signature, binding arguments to
    # the function, making the call to the function or formatting the results, then an
    # Exception will cause the nearby locations for the current destination to be an empty
    # list.
    #
    # Any nearby locations that were partially created will be lost in this function.
    except Exception:
        neighbors = []
    # FEATURED DESTINATION RESPONSE
    #
    # The response will have the source set to featured and will include the preset ID and
    # information about the resolved location.
    #
    # Photos and nearby locations will be included.
    #
    # confidence and recognition_mode will be set to None and confidence_calibrated will be
    # set to False.
    #
    # This is a curated match from a curated database and not a match based on an image. It
    # does not have machine learning confidence.
    return {'source': 'featured', 'preset_id': preset_id, 'confidence': None,
            'recognition_mode': None, 'confidence_calibrated': False,
            'landmark': {'id': identity, 'name': name, 'category_name': row.get('category_name'),
                'city': row.get('city'), 'state': row.get('state'), 'country': row.get('country'),
                'latitude': lat, 'longitude': lon, 'image': image},
            'landmark_photos': urls, 'nearby_landmarks': neighbors}


# FEATURED DESTINATION ENTRY POINT
#
# get_featured_destination() will first check to see if a preset has been defined.
#
# Then a cached payload will be checked for an unexpired value using the cache lock.
#
# If a cached value is found it will be moved to the end of the cache and the payload will
# be returned.
#
# The cached value is returned as is and not copied so if a caller manipulates the value it
# will also manipulate the value in the cache.
def get_featured_destination(preset_id, search, lookup, photos, nearby):
    if preset_id not in PRESETS:
        raise FeaturedUnavailable('This featured destination is not available.')
    with _lock:
        cached = _cache.get(preset_id)
        if cached and cached[0] > time.monotonic():
            _cache.move_to_end(preset_id)
            return cached[1]
    # RESOLVE A CACHE MISS
    #
    # If no valid cached value exists then a database location will be chosen and a payload
    # will be built outside of the lock.
    #
    # Failures of lookups or payloads will be propagated except in the case of optional-
    # nearby.
    #
    # Only a successfully constructed payload will be stored in the cache.
    row = choose_landmark(preset_id, search, lookup)
    payload = destination_payload(row, preset_id, photos, nearby)
    with _lock:
        # CACHE FOR ONE HOUR
        #
        # The payload will be stored with time.monotonic() + 3600 as its expiration time.
        #
        # The cache key will only use the preset ID. The database location and function
        # signatures will not be included in the cache key. Because of this database changes
        # may not be detected until cache expiry.
        #
        # Expired cache entries will be ignored on reads but will be replaced after a
        # successful cache resolution.
        _cache[preset_id] = (time.monotonic() + 3600, payload)
        # BOUND THE CACHE
        #
        # A maximum of the number of defined presets will be cached.
        #
        # When this maximum is exceeded the least recently used entry in the cache will be
        # removed.
        #
        # Cache hits will move values to the end of the cache. The cache is process-specific
        # and will be lost if a process is restarted.
        while len(_cache) > len(PRESETS):
            _cache.popitem(last=False)
    # RETURN THE DESTINATION
    #
    # A payload for the chosen featured location will be returned.
    #
    # This module resolves curated cards to database locations. Hotel, flight, restaurant
    # searches and image recognition are not done by this module. Landmark photos are
    # fetched through the supplied helper.
    return payload
