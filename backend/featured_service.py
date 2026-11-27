"""Resolve every map/gallery preset to its intended Neon landmark.

Names may use spaces, underscores, accents, or a translated landmark name.
Landmark IDs and photos always come from Neon. A confirmed landmark with
missing coordinates can use its preset's approximate geographic anchor;
that source is explicitly recorded in the response. Unrelated landmarks
and locations outside the intended region are never substituted.
"""
import inspect
import math
import re
import threading
import time
import unicodedata
from collections import OrderedDict
from collections.abc import Mapping


PRESETS = {
    'orlando': {
        'queries': ['Cinderella Castle', 'Magic Kingdom', 'Walt Disney World', 'Disney World'],
        'center': (28.42, -81.58), 'countries': ['USA', 'United States', 'United States of America', 'US'],
        'cities': ['Orlando', 'Bay Lake', 'Lake Buena Vista'],
    },
    'tokyo': {
        'queries': ['Tokyo Tower', 'Tokyo-tower', '東京タワー'],
        'center': (35.66, 139.75), 'countries': ['Japan', 'JP', '日本'], 'cities': ['Tokyo', 'Minato'],
    },
    'paris': {
        'queries': ['Eiffel Tower', 'Tour Eiffel', 'La Tour Eiffel'],
        'center': (48.86, 2.29), 'countries': ['France', 'FR'], 'cities': ['Paris'],
    },
    'amazon': {
        'queries': ['Amazon Theatre', 'Teatro Amazonas', 'Amazonas Theatre', 'Amazon Theater', 'Amazonas Theater'],
        'center': (-3.13, -60.02), 'countries': ['Brazil', 'Brasil', 'BR'], 'cities': ['Manaus'],
    },
    'rio': {
        'queries': ['Christ the Redeemer', 'Cristo Redentor', 'Christ Redeemer', 'Corcovado'],
        'center': (-22.95, -43.21), 'countries': ['Brazil', 'Brasil', 'BR'], 'cities': ['Rio de Janeiro'],
    },
    'new-york': {
        'queries': ['Statue of Liberty', 'Liberty Enlightening the World', 'Statue de la Liberte'],
        'center': (40.69, -74.04), 'countries': ['USA', 'United States', 'United States of America', 'US'],
        'cities': ['New York', 'New York City', 'NYC', 'Liberty Island'],
    },
    'great-wall': {
        'queries': ['Mutianyu', 'Great Wall of China', 'Great Wall', '万里长城'],
        'center': (40.43, 116.57), 'countries': ['China', 'CN', 'People\'s Republic of China'],
        'cities': ['Beijing', 'Huairou'],
    },
    'amalfi': {
        'queries': ['Amalfi Cathedral', 'Duomo di Amalfi', 'Cathedral of Amalfi', 'Cattedrale di Sant Andrea'],
        'center': (40.63, 14.60), 'countries': ['Italy', 'Italia', 'IT'], 'cities': ['Amalfi'],
    },
}

_cache = OrderedDict()
_lock = threading.Lock()


class FeaturedUnavailable(ValueError):
    pass


def words(value):
    """Normalize separators, case, category prefixes, and Latin accents."""
    value = unicodedata.normalize('NFKD', str(value or ''))
    value = ''.join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r'^\s*(?:category\s*:\s*)+', '', value, flags=re.I)
    return re.sub(r'[^\w]+', ' ', value.replace('_', ' '), flags=re.UNICODE).casefold().strip()


def phrase_in(phrase, value):
    return bool(phrase) and (' ' + phrase + ' ') in (' ' + value + ' ')


def coordinate(value, bound):
    if value is None or isinstance(value, bool) or (isinstance(value, str) and not value.strip()):
        return None
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return result if math.isfinite(result) and abs(result) <= bound else None


def match_rank(row, aliases):
    name, category = words(row.get('name')), words(row.get('category_name'))
    return max((100 if name == alias else 90 if category == alias
                else 75 if phrase_in(alias, name) else 65 if phrase_in(alias, category) else 0)
               for alias in aliases)


def choose_landmark(preset_id, search, lookup):
    config = PRESETS.get(preset_id)
    if config is None:
        raise FeaturedUnavailable('This featured destination is not available.')

    aliases = list(dict.fromkeys(words(query) for query in config['queries']))
    # Database searches are parameterized by database.py. Try spaced and
    # underscored forms because branch data uses both naming conventions.
    queries = list(dict.fromkeys(variant for alias in config['queries']
                                for variant in (alias, alias.replace(' ', '_'))))
    candidates = {}
    for query in queries:
        for original in search(query) or []:
            if not isinstance(original, Mapping) or original.get('landmark_id') is None:
                continue
            row = dict(original)
            rank = match_rank(row, aliases)
            if not rank:
                continue
            try:
                identity = int(row['landmark_id'])
            except (ValueError, TypeError, OverflowError):
                continue
            # Retain the strongest row for each actual database ID.
            if identity not in candidates or rank > candidates[identity][0]:
                candidates[identity] = (rank, row)

    anchor_lat, anchor_lon = config['center']
    possible = []
    for identity, (rank, summary) in sorted(candidates.items(), key=lambda item: (-item[1][0], item[0]))[:24]:
        detail = lookup(identity)
        if not isinstance(detail, Mapping) or not detail:
            continue
        row = {**summary, **{key: value for key, value in dict(detail).items()
                            if value is not None and value != ''}}
        # Identity must still refer to the candidate, rather than an unrelated row.
        try:
            if int(row.get('landmark_id')) != identity:
                continue
        except (ValueError, TypeError, OverflowError):
            continue
        lat = coordinate(row.get('lat'), 90)
        lon = coordinate(row.get('lon'), 180)
        # Never overwrite existing coordinates belonging to another region.
        if lat is not None and abs(lat - anchor_lat) > 2:
            continue
        if lon is not None and abs((lon - anchor_lon + 180) % 360 - 180) > 2:
            continue
        source = 'database'
        if lat is None or lon is None:
            country = words(row.get('country'))
            city = words(row.get('city'))
            country_matches = country in {words(value) for value in config['countries']}
            city_matches = any(phrase_in(words(value), city) for value in config['cities'])
            # A partial name match alone must not assign an invented location.
            # Require an exact name/category match plus country or city evidence.
            if rank < 90 or (country and not country_matches) or not (country_matches or city_matches):
                continue
            lat = anchor_lat if lat is None else lat
            lon = anchor_lon if lon is None else lon
            source = 'curated_anchor'
        row['lat'], row['lon'] = lat, lon
        row['coordinates_source'] = source
        distance = (lat - anchor_lat) ** 2 + ((lon - anchor_lon + 180) % 360 - 180) ** 2
        # Prefer genuine database coordinates before an approximate fallback.
        possible.append((source != 'database', -rank, distance, identity, row))

    if not possible:
        raise FeaturedUnavailable(
            f'The {preset_id} featured destination needs a matching Neon landmark with valid '
            'coordinates, or an exact landmark name/category and matching country or city. '
            'Check this preset’s landmark record in the database.'
        )
    possible.sort(key=lambda item: item[:4])
    return possible[0][4]


def destination_payload(row, preset_id, photos, nearby):
    identity = int(row['landmark_id'])
    name = row.get('name') or str(row.get('category_name') or '').replace('Category:', '').replace('_', ' ') or 'Featured landmark'
    urls = [url for url in photos(landmark_id=identity, limit=5) if isinstance(url, str) and url.strip()]
    image = row.get('url') or (urls[0] if urls else None)
    lat, lon = float(row['lat']), float(row['lon'])
    neighbors = []
    try:
        options = {'lat': lat, 'lon': lon, 'landmark_id': identity, 'exclude_landmark_id': identity,
                   'limit': 4, 'max_distance_km': 600.0}
        signature = inspect.signature(nearby)
        kwargs = options if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values()) else {key: value for key, value in options.items() if key in signature.parameters}
        signature.bind(**kwargs)
        for item in nearby(**kwargs) or []:
            if str(item.get('landmark_id')) == str(identity):
                continue
            neighbors.append({'id': item['landmark_id'], 'name': item.get('name') or str(item.get('category_name') or '').replace('Category:', '').replace('_', ' '),
                'city': item.get('city'), 'state': item.get('state'), 'country': item.get('country'),
                'latitude': item.get('lat'), 'longitude': item.get('lon'), 'image': item.get('url'),
                'distance_km': item.get('distance_km')})
            if len(neighbors) == 3:
                break
    except Exception:
        # Nearby recommendations are optional and cannot hide a valid preset.
        neighbors = []
    return {'source': 'featured', 'preset_id': preset_id, 'confidence': None,
            'recognition_mode': None, 'confidence_calibrated': False,
            'coordinates_source': row.get('coordinates_source', 'database'),
            'landmark': {'id': identity, 'name': name, 'category_name': row.get('category_name'),
                'city': row.get('city'), 'state': row.get('state'), 'country': row.get('country'),
                'latitude': lat, 'longitude': lon, 'image': image},
            'landmark_photos': urls, 'nearby_landmarks': neighbors}


def get_featured_destination(preset_id, search, lookup, photos, nearby):
    if preset_id not in PRESETS:
        raise FeaturedUnavailable('This featured destination is not available.')
    with _lock:
        cached = _cache.get(preset_id)
        if cached and cached[0] > time.monotonic():
            _cache.move_to_end(preset_id)
            return cached[1]
    row = choose_landmark(preset_id, search, lookup)
    payload = destination_payload(row, preset_id, photos, nearby)
    with _lock:
        _cache[preset_id] = (time.monotonic() + 600, payload)
        while len(_cache) > len(PRESETS):
            _cache.popitem(last=False)
    return payload
