import json
import urllib.request
import uuid

# Download webcams
url = "https://raw.githubusercontent.com/globetvapp/webcams/main/webcams.json"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read().decode())

new_cams = []
for c in data.get('webcams', []):
    cam = {
        "id": f"global_{c['id']}",
        "nome": c.get('name', 'Câmera Pública Global').upper(),
        "local": c.get('country', 'N/D'),
        "pais": c.get('country', 'N/D'),
        "setor": "GLOBAL",
        "tipo_area": c.get('scene', 'GERAL').upper(),
        "lat": c.get('lat'),
        "long": c.get('lon'),
        "status": "LIVE",
        "is_real_stream": True,
        "thumbnail_url": ""
    }
    
    if c.get('type') == 'youtube' and c.get('video_id'):
        cam["video_id"] = c.get('video_id')
        cam["url"] = f"https://www.youtube.com/watch?v={c.get('video_id')}"
    elif c.get('type') == 'hls' and c.get('src'):
        cam["url"] = c.get('src')
        # We don't have video_id for HLS
    
    new_cams.append(cam)

print(f"Found {len(new_cams)} cameras to import.")

# Append to live_cameras.json
with open('database/live_cameras.json', 'r') as f:
    db = json.load(f)

# Avoid duplicates by ID
existing_ids = {c['id'] for c in db}
added = 0
for c in new_cams:
    if c['id'] not in existing_ids:
        db.append(c)
        added += 1

with open('database/live_cameras.json', 'w') as f:
    json.dump(db, f, indent=2, ensure_ascii=False)

print(f"Added {added} new global cameras to the database!")
