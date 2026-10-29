import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import calendar
import hashlib
import html
from io import BytesIO
import json
from pathlib import Path
import re
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ml_model'))
from landmark_ml.storage import require_space

request_lock = threading.Lock()
next_request = 0.


def request(url):
    global next_request
    for attempt in range(4):
        try:
            with request_lock:
                time.sleep(max(0., next_request - time.monotonic()))
                next_request = time.monotonic() + .5
            with urlopen(Request(url, headers={'User-Agent': 'Trekmark-Capstone-Validation/1.0 (academic landmark recognition evaluation)'}), timeout=45) as response:
                body = response.read(12 * 1024 * 1024 + 1)
            if len(body) > 12 * 1024 * 1024:
                raise ValueError('Source response exceeds size limit')
            return body
        except HTTPError as error:
            if error.code in (404, 410) or attempt == 3:
                raise
            delay = max(30., float(error.headers.get('Retry-After', 30))) if error.code == 429 else 2 ** attempt
            time.sleep(min(120., delay))
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def plain(value):
    return html.unescape(re.sub('<[^>]+>', '', str(value or ''))).strip()


def capture_date(value):
    match = re.search(r'(20\d{2})[-:/.](\d{1,2})[-:/.](\d{1,2})',value)
    if match:
        try:
            return datetime(*map(int,match.groups())).date()
        except ValueError:
            return None
    months = {name.lower():i for i,name in enumerate(calendar.month_name) if name}
    match = re.search(r'(\d{1,2})\s+('+'|'.join(months)+r')\s+(20\d{2})',value,re.I)
    if match:
        day,month,year = match.groups()
        try:
            return datetime(int(year),months[month.lower()],int(day)).date()
        except ValueError:
            return None
    return None


def metadata(site, offset):
    query = {'action': 'query', 'format': 'json', 'generator': 'search',
             'gsrsearch': site.get('search', f'"{site["query"]}" (2022 OR 2023 OR 2024 OR 2025) filetype:bitmap'),
             'gsrnamespace': 6, 'gsrlimit': 100, 'gsroffset': offset,
             'gsrsort': site.get('sort', 'relevance'),
             'prop': 'imageinfo', 'iiprop': 'url|extmetadata', 'iiurlwidth': 960}
    for attempt in range(5):
        data = json.loads(request('https://commons.wikimedia.org/w/api.php?' + urlencode(query)))
        if 'error' not in data:
            return list(data.get('query', {}).get('pages', {}).values())
        if attempt == 4:
            raise ValueError(data['error'].get('info', 'Source search failed'))
        time.sleep(2 ** (attempt + 1))


def collect(root, sites, per_site, exclude=(), max_offset=300):
    root.mkdir(parents=True, exist_ok=True)
    (root / 'images').mkdir(exist_ok=True)
    manifest = root / 'collection.json'
    rows = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else []
    failures = []
    seen_titles = {row['source_title'] for row in rows}
    seen_hashes = {row['sha256'] for row in rows}
    excluded_groups = {}
    for previous in exclude:
        for row in json.loads(previous.read_text(encoding='utf-8')):
            seen_titles.add(row['source_title'])
            seen_hashes.add(row['sha256'])
            author = re.sub('[^a-z0-9]', '', row['source_author'].lower())
            excluded_groups.setdefault((row['site'],author),[]).append(capture_date(row['capture_date']))
    for site in sites:
        counts = Counter(row['source_author'] for row in rows if row['site'] == site['name'])
        for offset in range(0, max_offset, 100):
            if sum(row['site'] == site['name'] for row in rows) >= per_site:
                break
            candidates = []
            try:
                pages = metadata(site, offset)
            except Exception as error:
                failures.append({'site': site['name'], 'error': str(error)})
                (root / 'download-failures.json').write_text(json.dumps(failures, indent=2), encoding='utf-8')
                break
            for page in pages:
                if page['title'] in seen_titles or not page.get('imageinfo'):
                    continue
                if site.get('title_aliases'):
                    title = re.sub('[^a-z0-9]', '', page['title'].lower())
                    if not any(re.sub('[^a-z0-9]', '', alias.lower()) in title for alias in site['title_aliases']):
                        continue
                    if any(word in page['title'].lower() for word in ('replica', 'painting', 'model of', 'souvenir')):
                        continue
                info = page['imageinfo'][0]
                fields = {key: plain(value.get('value')) for key, value in info.get('extmetadata', {}).items()}
                date = fields.get('DateTimeOriginal', '')
                years = re.findall(r'\b(20\d{2})\b', date)
                if not years or not 2020 <= int(years[0]) <= datetime.now().year:
                    continue
                author = fields.get('Artist', '')
                license_name = fields.get('LicenseShortName', '')
                if not author or not (license_name.startswith('CC') or 'ublic domain' in license_name):
                    continue
                previous_dates = excluded_groups.get((site['name'],re.sub('[^a-z0-9]', '', author.lower())),[])
                taken = capture_date(date)
                if previous_dates and (taken is None or any(previous is None or abs((taken-previous).days)<=31 for previous in previous_dates)):
                    continue
                if counts[author] >= 3:
                    continue
                counts[author] += 1
                candidates.append((page['title'], info, fields))
                if len(candidates) + sum(row['site'] == site['name'] for row in rows) >= per_site:
                    break
            def download(candidate):
                title, info, fields = candidate
                try:
                    body = request(info.get('thumburl', info['url']))
                    with Image.open(BytesIO(body)) as image:
                        image.verify()
                    digest = hashlib.sha256(body).hexdigest()
                    return candidate, body, digest, None
                except Exception as error:
                    return candidate, None, None, type(error).__name__
            with ThreadPoolExecutor(max_workers=3) as pool:
                for (title, info, fields), body, digest, error in pool.map(download, candidates):
                    seen_titles.add(title)
                    if error or digest in seen_hashes:
                        failures.append({'title': title, 'error': error or 'duplicate'})
                        continue
                    seen_hashes.add(digest)
                    require_space(root, len(body))
                    path = root / 'images' / (digest[:24] + '.jpg')
                    path.write_bytes(body)
                    rows.append({'site': site['name'], 'expected_name': site['name'],
                                 'landmark_ids': site['landmark_ids'], 'ground_truth_verified': False,
                                 'image_path': path.relative_to(root).as_posix(), 'split': 'test',
                                 'sha256': digest, 'source_title': title, 'source_url': info['descriptionurl'],
                                 'original_url': info['url'], 'download_url': info.get('thumburl', info['url']),
                                 'source_author': fields['Artist'], 'capture_date': fields['DateTimeOriginal'],
                                 'license': fields['LicenseShortName'], 'license_url': fields.get('LicenseUrl'),
                                 'source_description': fields.get('ImageDescription', ''),
                                 'group_id': site['name'] + ':' + fields['Artist'] + ':' + (capture_date(fields['DateTimeOriginal']).strftime('%Y-%m') if capture_date(fields['DateTimeOriginal']) else 'unknown')})
            manifest.write_text(json.dumps(rows, ensure_ascii=True, indent=2), encoding='utf-8')
            (root / 'download-failures.json').write_text(json.dumps(failures, indent=2), encoding='utf-8')
            print(json.dumps({'site': site['name'], 'collected': sum(row['site'] == site['name'] for row in rows), 'total': len(rows)}), flush=True)
            time.sleep(.5)
    return rows


def contact_sheets(root, rows):
    for site in dict.fromkeys(row['site'] for row in rows):
        group = [row for row in rows if row['site'] == site]
        canvas = Image.new('RGB', (1200, 260 * ((len(group) + 4) // 5)), 'white')
        draw = ImageDraw.Draw(canvas)
        for number, row in enumerate(group):
            with Image.open(root / row['image_path']) as image:
                tile = ImageOps.contain(ImageOps.exif_transpose(image).convert('RGB'), (234, 220))
            x, y = (number % 5) * 240, (number // 5) * 260
            canvas.paste(tile, (x, y))
            draw.text((x+2, y+222), str(number) + ' ' + row['sha256'][:12], fill='black')
        canvas.save(root / (re.sub('[^a-z0-9]+', '-', site.lower()).strip('-') + '-sheet.jpg'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('sites', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--per-site', type=int, default=30)
    parser.add_argument('--exclude', type=Path, nargs='*', default=[])
    parser.add_argument('--max-offset', type=int, default=300)
    args = parser.parse_args()
    if args.per_site < 1:
        parser.error('Photo count must be positive')
    rows = collect(args.output.resolve(), json.loads(args.sites.read_text(encoding='utf-8')), args.per_site, args.exclude, args.max_offset)
    contact_sheets(args.output.resolve(), rows)


if __name__ == '__main__':
    main()
