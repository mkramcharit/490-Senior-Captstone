"""Photos from a free Wikimedia Commons place using conservative matching and attribution.
A Wikimedia API key or billing account is not required. If a match is missing or unknown, the existing state of the hotel's photo is maintained."""

# IMPORTS
# These import modules handle remote text cleaning, name and location matching,
# API calls, error logging, and a shared cache used by threads within this module.
import html

import logging

import math

import os

import re

import threading

import time

import unicodedata

from collections import OrderedDict

from urllib.parse import urlparse, urlunparse

import httpx

# WIKIMEDIA CONFIGURATION
# Search for files and retrieve image information using the Commons API.
# When making API calls to Wikimedia, use the User-Agent Trekmark.
COMMONS_API = "https://commons.wikimedia.org/w/api.php"

# Specify a real project and provide a contact page to Wikimedia.
# A specific deployment configuration may override this.

USER_AGENT = os.getenv("WIKIMEDIA_USER_AGENT", "").strip() or (

    "TrekmarkCapstone/1.1 "

    "(https://github.com/mkramcharit/490-Senior-Captstone) "

    f"httpx/{httpx.__version__}"

)

# SHARED CACHE AND LOCK
# Cache recent photo matches and mismatches.
# A lock is used to ensure only one batch of photo lookups can run within
# this Python process.
# HTTP requests have a default timeout of eight seconds.
_logger = logging.getLogger(__name__)

_cache = OrderedDict()

_lock = threading.Lock()

_TIMEOUT = 8.0

# CLEAN REMOTE DATA
# Decode character entities and strip HTML tags to create display text.
# This text should be rendered and not injected as HTML in the frontend.
def _plain(value):

    """Remote data should be treated as text and not rendered as HTML in React."""

    return html.unescape(re.sub(r"<[^>]*>", " ", str(value or ""))).strip()

# NORMALIZE TEXT FOR MATCHING
# Break apart Unicode characters and apply case and accent insensitive normalization.
# Remove combining accents.
# Extract matching name tokens.
def _words(value):

    normalized = unicodedata.normalize("NFKD", _plain(value)).casefold()

    return re.findall(r"[^\W_]+", "".join(c for c in normalized if not unicodedata.combining(c)))

# READ ONE REMOTE DATA FIELD
# Commons stores fields like description, license, and author in extmetadata.
# Return cleaned text or an empty string if the field is not present.
def _metadata(info, key):

    item = info.get("extmetadata", {}).get(key, {})

    return _plain(item.get("value", "")) if isinstance(item, dict) else ""

# VALIDATE LINKS
# Accept HTTPS links that have a hostname and do not contain credentials.
# If a hostname is provided, require that the hostname match exactly.
def _url(value, host=None):

    if not isinstance(value, str):

        return None

    try:

        parsed = urlparse(value)

        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:

            return None

        if host and parsed.hostname != host:

            return None

        return value

    except ValueError:

        return None

# DISTANCE CALCULATION
# Calculate a distance using the haversine formula to get a distance in meters.
# This is used to reject photos of places that are too far from the target place.
def _distance(lat1, lon1, lat2, lon2):

    a, b = math.radians(lat1), math.radians(lat2)

    term = math.sin((b-a)/2)**2 + math.cos(a)*math.cos(b)*math.sin(math.radians(lon2-lon1)/2)**2

    return 6371000 * 2 * math.asin(math.sqrt(min(1, max(0, term))))

# VALIDATE A POSSIBLE PHOTO
# Check the photo's hotel name, location evidence, author, reusable license,
# image URL, source page, and file type before accepting the photo.
def _candidate(page, hotel):

    """Require both name and location and a supported reusable license."""

    # Require at least one imageinfo object before reading image information.
    infos = page.get("imageinfo")

    if not isinstance(infos, list) or not infos or not isinstance(infos[0], dict):

        return None

    info = infos[0]

    # Only JPEG, PNG and WebP images are supported by this lookup.
    if info.get("mime") not in ("image/jpeg", "image/png", "image/webp"):

        return None

    # Create matching text from the image description and the image title.
    title = " ".join(_words(page.get("title", "")))

    description = " ".join(_words(_metadata(info, "ImageDescription")))

    text = f"{title} {description}"

    # Support both translated and native names.
    # Geographic matching should be independent from matching of names so a
    # missing city word will not mask valid photos.

    aliases = [hotel.get("name"), *(hotel.get("name_aliases") or [])]

    all_name_words = set()

    matched_names = []

    # A name is matched if all meaningful words from the name exist in the combined
    # photo text. Articles may be ignored when matching aliases.
    for alias in aliases:

        words = [word for word in _words(alias) if word not in {"the", "a", "an"}]

        all_name_words.update(words)

        if words and all(word in set(text.split()) for word in words):

            matched_names.append(words)

    if not matched_names:

        return None

    # If multiple aliases match, use the longest match for matching and ranking.
    name_words = max(matched_names, key=len)

    # A photo FROM a hotel is not necessarily a photo OF the hotel.

    if re.search(r"\b(?:views?|taken|seen) from\b", title):

        return None

    # If coordinates are present, reject a photo with a wrong namesake based on
    # geography.

    distances = []

    for coordinate in page.get("coordinates", []):

        try:

            lat, lon = float(coordinate["lat"]), float(coordinate["lon"])

            if math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:

                distances.append(_distance(float(hotel["latitude"]), float(hotel["longitude"]), lat, lon))

        except (KeyError, ValueError, TypeError, OverflowError):

            continue

    # If valid photo coordinates exist, reject the photo if the nearest of the
    # coordinates is further than 300 meters from the hotel.
    if distances and min(distances) > 300:

        return None

    # Categories may contain neighborhood information even if the caption does not.

    location_text = text + " " + " ".join(_words(_metadata(info, "Categories")))

    localities = [hotel.get("city"), *(hotel.get("location_names") or [])]

    locality_matches = any(

        (locality := " ".join(_words(value))) and

        re.search(r"\b" + re.escape(locality) + r"\b", location_text)

        for value in localities

    )

    # International addresses may place the neighborhood and postal code before the
    # country e.g. Shibakoen 1 105-8511, Japan.
    # Ignore the country, digits and hotel-name words as location evidence.

    address_parts = str(hotel.get("address") or "").split(",")

    if not locality_matches and len(address_parts) >= 3:

        country_words = set(_words(hotel.get("country")))

        address_words = _words(re.sub(r"\d+", " ", address_parts[-2]))

        locality_matches = any(

            len(word) >= 4 and word not in all_name_words and word not in country_words

            and word in set(location_text.split())

            for word in address_words

        )

    # A one-word chain name still may require coordinates.
    # If coordinates are not usable then require a matching name with at least two
    # meaningful words and locality evidence.
    if not distances and (not locality_matches or len(name_words) < 2):

        return None

    # LICENSE VALIDATION
    # Normalize the license and accept CC0, CC BY, CC BY-SA or public domain.
    # Reject non-free images.
    license_name = _metadata(info, "LicenseShortName")

    license_code = license_name.casefold().replace("-", " ")

    if not re.fullmatch(r"(?:cc by(?: sa)? \d\.\d|cc0(?: 1\.0)?|public domain)", license_code):

        return None

    if _metadata(info, "NonFree").casefold() in {"true", "1", "yes"}:

        return None

    # Prefer the original upload. The host for thumbnails can reject a potentially
    # valid image request. Only allow hosts from Wikimedia.

    image = next((url for value in (info.get("url"), info.get("thumburl"))

                  for host in ("upload.wikimedia.org", "thumb.wikimedia.org")

                  if (url := _url(value, host))), None)

    # Commons may add query parameters for analytics to a link to the original image.
    # Some image servers will reject this with an HTTP 403. Instead use the
    # verified image hosted on Wikimedia. Use the canonical URL without a fragment
    # or tracking parameters.

    if image:

        parsed_image = urlparse(image)

        image = urlunparse((parsed_image.scheme, parsed_image.netloc,

                            parsed_image.path, "", "", ""))

    # ATTRIBUTION DATA
    # Read the author, license link and source page from the Commons page.
    # Require author, source, and image information as well as a license link for
    # CC licenses.
    source = _url(info.get("descriptionurl"), "commons.wikimedia.org")

    license_url = _url(_metadata(info, "LicenseUrl"))

    author = _metadata(info, "Artist")

    if not image or not source or not author:

        return None

    if license_code.startswith("cc") and not license_url:

        return None

    # Return the matched photo along with its attribution data.
    # _score is an internal ranking field and is stripped before returning a match.
    return {

        "image": image,

        "image_source": source,

        "image_author": author,

        "image_license": license_name,

        "image_license_url": license_url,

        "image_provider": "Wikimedia Commons",

        "image_title": _plain(page.get("title", "")).removeprefix("File:"),

        # A title match should be ranked higher than a mention in a long description.

        "_score": (all(word in set(title.split()) for word in name_words), bool(distances)),

    }

# SEARCH FOR A SINGLE HOTEL ON COMMONS
# Create a narrowed search using the provided names, request up to six file
# pages and validate each possible photo. Choose the highest ranking photo.
def find_hotel_photo(hotel, client):

    """Make one bounded API call per hotel. Do not scrape hotel websites."""

    aliases = [hotel.get("name"), *(hotel.get("name_aliases") or [])]

    # Normalize and deduplicate names, but maintain the relative order of the names.
    # Keep no more than eight names and remove any empty normalized names.
    names = list(dict.fromkeys(" ".join(_words(value)) for value in aliases if value))[:8]

    names = [name for name in names if name]

    if not names:

        return None

    # If a Latin name is provided by Geoapify then prefer this. Commons titles
    # commonly use these names. Keep all aliases for use in photo validation.
    # A narrowed search avoids an expensive OR of many possible translations.

    preferred = next((name for name in names if re.search(r"[a-z]", name)

                      and not re.search(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", name)), names[0])

    query = f'"{preferred}"'

    # Search in namespace 6 which contains files. Request the file type,
    # available image URLs, coordinates, extended metadata, and imageinfo.
    # An 800 pixel image thumbnail is requested along with the original image.
    response = client.get(COMMONS_API, params={

        "action": "query", "format": "json", "formatversion": 2,

        "generator": "search", "gsrsearch": query, "gsrnamespace": 6,

        "gsrlimit": 6, "prop": "imageinfo|coordinates", "colimit": "max",

        "iiprop": "url|mime|extmetadata", "iiurlwidth": 800,

    })

    # Throw an exception on a failed HTTP response before parsing JSON.
    response.raise_for_status()

    payload = response.json()

    # An invalid response or an API error indicates a search failure.
    if not isinstance(payload, dict) or "error" in payload:

        raise ValueError("Wikimedia search unavailable")

    pages = payload.get("query", {}).get("pages", [])

    # Validate each returned file page and reject any invalid pages.
    matches = [_candidate(page, hotel) for page in pages if isinstance(page, dict)]

    matches = [match for match in matches if match]

    if not matches:

        return None

    # Choose the highest ranked tuple. Title-name matches are preferred over
    # mentions in long descriptions. Usefulness of coordinates is used as a tie-breaker.
    # Strip out the internal score.
    match = max(matches, key=lambda item: item["_score"])

    match.pop("_score")

    return match

# ADD PHOTOS TO A BATCH OF PLACES
# Reuse matches from cache if available and make requests sequentially.
# A provider limit and deadline can help to bound photo-only searches.
def enrich_hotel_photos(hotels, max_photos=None, deadline=None):

    """Make requests to Wikimedia sequentially and cache both matches and mismatches.
    This lookup is shared between hotel and restaurant sections. Wait up to
    30 seconds for an active batch so simultaneous sections can avoid losing
    photos silently.
    Upstream requests still have individual timeouts."""

    # Wait up to 30 seconds for a batch lock or less if a deadline is provided.
    # Return the original hotels if a lock was not obtained.
    lock_wait = 30 if deadline is None else max(0, min(30, deadline - time.monotonic()))

    if not hotels or not _lock.acquire(timeout=lock_wait):

        return hotels

    try:

        # Make use of a single HTTP client for the batch and use the project’s User-Agent.
        # Do not follow redirects automatically.
        with httpx.Client(timeout=_TIMEOUT, follow_redirects=False,

                          headers={"User-Agent": USER_AGENT}) as client:

            output = []

            photo_count = 0

            # Use the caller’s deadline if provided. Otherwise provide a default 25
            # second search budget after the batch client has been created.
            deadline = deadline if deadline is not None else time.monotonic() + 25

            for hotel in hotels:

                # Bound searches in photo only mode including searches with many possible
                # photos.

                if max_photos is not None and (photo_count >= max_photos or time.monotonic() >= deadline):

                    break

                # Identify a cached lookup using the place ID, name, aliases, city and
                # coordinates. Different aspects of a place should not share a wrong result.
                key = (hotel["id"], hotel.get("name"), hotel.get("city"),

                       hotel.get("latitude"), hotel.get("longitude"),

                       tuple(hotel.get("name_aliases") or []))

                cached = _cache.get(key)

                # Use an unexpired cache entry and mark it as recently used.
                # Merge photo fields into the place and count the number of images.
                # Skip another API call. If a cached lookup was a miss then existing fields
                # are maintained.
                if cached and cached[0] > time.monotonic():

                    _cache.move_to_end(key)

                    output.append({**hotel, **(cached[1] or {})})

                    photo_count += bool(output[-1].get("image"))

                    continue

                try:

                    # Timeouts are limited by the remaining search budget with a minimum timeout
                    # of 0.1 seconds.
                    client.timeout = httpx.Timeout(max(0.1, min(_TIMEOUT, deadline - time.monotonic())))

                    photo = find_hotel_photo(hotel, client)

                # On a timeout record the name of the place, keep the original place information
                # and continue to the next place. Do not cache this as a miss.
                except httpx.TimeoutException:

                    _logger.warning("Wikimedia place photo lookup timed out for %s", hotel.get("name"))

                    output.append(hotel)

                    continue

                except (httpx.HTTPError, ValueError, TypeError, AttributeError, KeyError) as error:

                    # Record the status/type of the failure without recording full URLs.
                    # This allows differentiation between an upstream failure and the absence of
                    # a matching photo.

                    response = getattr(error, "response", None)

                    status = response.status_code if response is not None else "none"

                    _logger.warning("Wikimedia place photo lookup failed: %s, HTTP %s",

                                    type(error).__name__, status)

                    # Stop this batch on a failure from a provider or response. Do not initiate a
                    # retry storm.
                    # Return partial results and keep the places that have not been processed yet.
                    output.extend(hotels[len(output):])

                    return output

                # CACHE MATCHES AND MISSES
                # Cache a successful photo match for 24 hours. Cache a completed search with
                # no successful photo match for one hour to avoid repeating the same failed search.
                _cache[key] = (time.monotonic() + (86400 if photo else 3600), photo)

                # Keep at most 512 cached entries and remove the least recently used.
                while len(_cache) > 512:

                    _cache.popitem(last=False)

                # Merge any matched photo and credits into the place.
                # Add a place with an image to the optional photo count.
                output.append({**hotel, **(photo or {})})

                photo_count += bool(output[-1].get("image"))

            return output

    # If an import or HTTP error occurs at this outer handler then return the
    # original list. Module level import errors occur before this handler.
    except (httpx.HTTPError, ImportError):

        return hotels

    # Always release the batch lock even on exceptions or early returns.
    finally:

        _lock.release()
