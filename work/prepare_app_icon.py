"""Convert the supplied square image into a multi-resolution Windows icon."""
import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT=Path(__file__).resolve().parent.parent
source=ROOT/'assets/app-icon-source.jpg'
sizes=[16,24,32,48,64,128,256]
image=Image.open(source).convert('RGBA')
assert image.width == image.height
destination=ROOT/'assets/app.ico'
image.save(destination,sizes=[(edge,edge) for edge in sizes])
image.resize((256,256),Image.Resampling.LANCZOS).save(ROOT/'work/app-icon-preview.png')
metadata={'source':'app-icon-source.jpg','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
    'conversion':'original complete square image; Lanczos resizing; ICO format conversion only',
    'icon':'app.ico','sizes':sizes,'sha256':hashlib.sha256(destination.read_bytes()).hexdigest()}
(ROOT/'assets/app-icon.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
print(json.dumps(metadata,indent=2))
