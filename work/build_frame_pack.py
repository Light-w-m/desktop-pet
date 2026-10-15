"""Build independently compressed native RGBA and display-ready BGRA frames."""
from pathlib import Path
import hashlib
import json
import zlib

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parent.parent
stage = ROOT/'work'/'repaired-assets'
manifest = json.loads((stage/'manifest.json').read_text(encoding='utf-8'))
index = {'version': 1, 'canvas': manifest['canvas'], 'display_canvas': manifest['display_canvas'],
         'data': 'pet-frames.bin', 'animations': {}}


def record(stream, rgba, premultiply=False):
    box = rgba.getbbox()
    tile = rgba.crop(box)
    if premultiply:
        r, g, b, a = tile.split()
        pixels = Image.merge('RGBA', (ImageChops.multiply(r, a), ImageChops.multiply(g, a),
                                      ImageChops.multiply(b, a), a)).tobytes('raw', 'BGRA')
    else:
        pixels = tile.tobytes()
    data = zlib.compress(pixels, 3)
    result = [stream.tell(), len(data), *box]
    stream.write(data)
    return result


with (stage/'pet-frames.bin').open('wb') as output:
    for name, spec in manifest['animations'].items():
        frames = []
        source = stage/spec['file']
        with Image.open(source) as animation:
            for number in range(animation.n_frames):
                animation.seek(number)
                rgba = animation.convert('RGBA')
                native = record(output, rgba)
                display = record(output, rgba.resize(tuple(index['display_canvas']), Image.Resampling.LANCZOS), True)
                frames.append({'ms': animation.info['duration'], 'native': native, 'display': display})
        assert len(frames) == spec['frames']
        assert sum(f['ms'] for f in frames) == spec['duration_ms']
        index['animations'][name] = {'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'frames': frames}
        print(name, len(frames), 'pack MiB', round(output.tell()/1024/1024, 1), flush=True)
index['data_bytes'] = (stage/'pet-frames.bin').stat().st_size
(stage/'pet-frames.json').write_text(json.dumps(index, separators=(',', ':'))+'\n', encoding='utf-8')
manifest['playback_pack'] = 'pet-frames.json'
manifest['version'] = 6
(stage/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
print('Pack complete', index['data_bytes'], flush=True)
