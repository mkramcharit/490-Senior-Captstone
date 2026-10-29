import argparse
from collections import Counter
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
from urllib.parse import urlencode

from PIL import Image

from collect_web_photos import capture_date, contact_sheets, request, require_space


def collect(sites, root, previous, per_site=15):
    root.mkdir(parents=True,exist_ok=True)
    (root/'images').mkdir(exist_ok=True)
    output=root/'collection.json'
    rows=json.loads(output.read_text()) if output.exists() else []
    old=json.loads(previous.read_text(encoding='utf-8'))
    excluded_hashes={row['sha256'] for row in old}
    seen={row['source_url'] for row in rows}
    errors=[]
    for site in sites:
        counts=Counter(row['source_author'] for row in rows if row['site']==site['name'])
        for tag in site['flickr_tags']:
            if sum(row['site']==site['name'] for row in rows)>=per_site:
                break
            try:
                feed=json.loads(request('https://www.flickr.com/services/feeds/photos_public.gne?'+urlencode({'tags':tag,'format':'json','nojsoncallback':1})))
            except Exception as error:
                errors.append({'site':site['name'],'error':type(error).__name__})
                continue
            for item in feed.get('items',[]):
                if sum(row['site']==site['name'] for row in rows)>=per_site:
                    break
                if item['link'] in seen:
                    continue
                seen.add(item['link'])
                taken=capture_date(item['date_taken'])
                if taken is None or taken.year<2020:
                    continue
                try:
                    info=json.loads(request('https://www.flickr.com/services/oembed/?'+urlencode({'url':item['link'],'format':'json','maxwidth':1024})))
                    author=info['author_name']
                    if counts[author]>=3:
                        continue
                    key=re.sub('[^a-z0-9]','',author.lower())
                    dates=[capture_date(row['capture_date']) for row in old if row['site']==site['name'] and re.sub('[^a-z0-9]','',row['source_author'].lower())==key]
                    if any(date is None or abs((taken-date).days)<=31 for date in dates):
                        continue
                    body=request(info['url'])
                    with Image.open(BytesIO(body)) as image:
                        image.verify()
                    digest=hashlib.sha256(body).hexdigest()
                    if digest in excluded_hashes or any(row['sha256']==digest for row in rows):
                        continue
                    counts[author]+=1
                    require_space(root,len(body))
                    path=root/'images'/(digest[:24]+'.jpg')
                    path.write_bytes(body)
                    rows.append({'site':site['name'],'expected_name':site['name'],'landmark_ids':site['landmark_ids'],
                                 'ground_truth_verified':False,'split':'test','sha256':digest,
                                 'image_path':path.relative_to(root).as_posix(),'source_provider':'Flickr',
                                 'source_url':item['link'],'original_url':info['url'],'download_url':info['url'],
                                 'source_title':item['title'],'source_description':item.get('tags',''),
                                 'source_author':author,'source_author_id':item['author_id'],'capture_date':item['date_taken'],
                                 'license':info.get('license','See source photo page'),'usage':'Local evaluation; photos are not included in sharing packages',
                                 'group_id':site['name']+':'+author+':'+taken.strftime('%Y-%m')})
                    output.write_text(json.dumps(rows,indent=2),encoding='utf-8')
                except Exception as error:
                    errors.append({'site':site['name'],'source':item['link'],'error':type(error).__name__})
            print(json.dumps({'site':site['name'],'collected':sum(row['site']==site['name'] for row in rows),'total':len(rows)}),flush=True)
        (root/'download-failures.json').write_text(json.dumps(errors,indent=2),encoding='utf-8')
    contact_sheets(root,rows)
    return rows


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('sites',type=Path)
    parser.add_argument('previous',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--per-site',type=int,default=15)
    args=parser.parse_args()
    collect(json.loads(args.sites.read_text()),args.output.resolve(),args.previous,args.per_site)


if __name__=='__main__':
    main()
