"""Verify the packed frames against the original complete lossless animation."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from PIL import Image
from frame_stream import FrameArchive, pack_frame

stage = ROOT/'work'/'repaired-assets'
archive = FrameArchive(stage/'pet-frames.json')
manifest = json.loads((stage/'manifest.json').read_text(encoding='utf-8'))
index = json.loads((stage/'pet-frames.json').read_text(encoding='utf-8'))
report = {}
for name, spec in manifest['animations'].items():
    source = stage/spec['file']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == index['animations'][name]['source_sha256']
    checked_sizes = 0
    with Image.open(source) as animation:
        for number in range(animation.n_frames):
            animation.seek(number)
            rgba = animation.convert('RGBA')
            assert archive.read(name, number, (560,480)) == pack_frame(rgba.resize((560,480),Image.Resampling.LANCZOS)), (name, number)
            if number % 71 == 0 or number == animation.n_frames-1:
                for size in ((336,288),(392,336),(728,624),(840,720)):
                    assert archive.read(name,number,size) == pack_frame(rgba.resize(size,Image.Resampling.LANCZOS)), (name,number,size)
                    checked_sizes += 1
        for number in (animation.n_frames-1,0,animation.n_frames//2,1):
            animation.seek(number)
            assert archive.read(name,number,(560,480)) == pack_frame(animation.convert('RGBA').resize((560,480),Image.Resampling.LANCZOS))
    report[name] = {'frames_verified': animation.n_frames, 'pixel_differences':0,'other_sizes_verified':checked_sizes,'random_seeks_verified':4}
    print(name, report[name], flush=True)
(ROOT/'work'/'stream-quality-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
