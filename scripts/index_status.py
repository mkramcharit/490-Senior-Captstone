import json
import sqlite3
from pathlib import Path

root = Path(__file__).resolve().parents[1] / 'artifacts' / 'full-neon'
connection = sqlite3.connect((root / 'ledger.sqlite').resolve().as_uri() + '?mode=ro', uri=True)
source = connection.execute("SELECT value FROM metadata WHERE key='source_counts'").fetchone()
result = {'source': json.loads(source[0]) if source else None,
          'counts': dict(connection.execute('SELECT state,count(*) FROM images GROUP BY state')),
          'indexed_landmarks': connection.execute("SELECT count(DISTINCT landmark_id) FROM images WHERE state='indexed'").fetchone()[0],
          'bundle_exists': (root / 'bundle' / 'landmarks.index').is_file()}
print(json.dumps(result, indent=2))
connection.close()
