"""Build a pixel-exact native-only pack with short lossless WebP delta chains."""
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import zlib

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from PIL import Image,ImageChops
from frame_stream import FrameArchive

GROUP=8
STANDING_ENTRY_KEYS=24  # Cover the full .24-second return and its decoder lookahead.


def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):
            value.update(block)
    return value.hexdigest()


def inputs(root):
    manifest=json.loads((root/'assets/manifest.json').read_text(encoding='utf-8'))
    paths=[root/'assets/manifest.json',Path(__file__)]
    paths += [root/'assets'/spec['file'] for spec in manifest['animations'].values()]
    for name in ('dragging','stomping','walking'):
        paths += [root/'assets'/name/file for file in ('pet-frames.json','pet-frames.bin','source.json')]
    return {str(path.relative_to(root)).replace('\\','/'):{'bytes':path.stat().st_size,'sha256':digest(path)}
            for path in paths}


def encode(number,raw,box,previous,previous_box):
    image=Image.frombytes('RGBA',(box[2]-box[0],box[3]-box[1]),raw)
    def webp(source):
        buffer=io.BytesIO()
        source.save(buffer,format='WEBP',lossless=True,exact=True,method=1,quality=90)
        encoded=buffer.getvalue()
        # Preserve RGB beneath transparency too; this matters before resizing.
        with Image.open(io.BytesIO(encoded)) as decoded:
            assert decoded.convert('RGBA').tobytes() == source.tobytes()
        return encoded
    full=webp(image)
    if number % GROUP == 0:
        return full,False
    aligned=Image.new('RGBA',image.size)
    aligned.paste(Image.frombytes('RGBA',(previous_box[2]-previous_box[0],previous_box[3]-previous_box[1]),previous),
                  (previous_box[0]-box[0],previous_box[1]-box[1]))
    delta=webp(ImageChops.subtract_modulo(image,aligned))
    return (delta,True) if len(delta) < len(full) else (full,False)


def build(root=ROOT,output=None):
    output=output or root/'work'/'repaired-assets'
    output.mkdir(parents=True,exist_ok=True)
    signature=inputs(root)
    existing=output/'pet-frames.json'
    if existing.is_file():
        current=json.loads(existing.read_text(encoding='utf-8'))
        data=output/current['data']
        if (current.get('version') == 2 and current.get('source_files') == signature and
                data.is_file() and data.stat().st_size == current['data_bytes']):
            print('Compact pack is up to date.',flush=True)
            return output
    manifest=json.loads((root/'assets/manifest.json').read_text(encoding='utf-8'))
    index={'version':2,'codec':'webp-lossless-native-delta','canvas':manifest['canvas'],
           'display_canvas':manifest['display_canvas'],'data':'pet-frames.bin','animations':{},
           'source_files':signature,'max_dependency_depth':GROUP-1}
    temporary=output/'pet-frames.part.bin'
    with temporary.open('wb') as packed,ThreadPoolExecutor(max_workers=4) as pool:
        for name in (*manifest['animations'],'dragging','stomping','walking_left','walking_right'):
            frames=[]
            def source_frames():
                if name in manifest['animations']:
                    spec=manifest['animations'][name]
                    with Image.open(root/'assets'/spec['file']) as animation:
                        for number in range(animation.n_frames):
                            animation.seek(number)
                            rgba=animation.convert('RGBA');box=rgba.getbbox()
                            yield int(animation.info['duration']),rgba.crop(box).tobytes(),box
                else:
                    folder='walking' if name.startswith('walking_') else name
                    archive=FrameArchive(root/'assets'/folder/'pet-frames.json')
                    with archive.sources[name].open('rb') as source:
                        for frame in archive.animations[name]['frames']:
                            offset,length,*box=frame['native']
                            source.seek(offset)
                            yield frame['ms'],zlib.decompress(source.read(length)),tuple(box)
            jobs=deque()
            previous=previous_box=None
            def write_one():
                number,ms,box,future=jobs.popleft()
                encoded,delta=future.result()
                depth=frames[-1]['depth']+1 if delta else 0
                record={'ms':ms,'native':[packed.tell(),len(encoded),*box],
                        'base':number-1 if delta else None,'depth':depth}
                assert depth < GROUP
                packed.write(encoded);frames.append(record)
            for number,(ms,raw,box) in enumerate(source_frames()):
                # The reaction and first idle frames overlap during recovery.
                # Keep both sides independent: rebuilding an evicted idle
                # dependency chain otherwise stalls the last reaction frames.
                independent=name == 'stomping' or name.startswith('walking_') or (name == 'standing' and number < STANDING_ENTRY_KEYS)
                key_number=0 if independent else number
                jobs.append((number,ms,box,pool.submit(encode,key_number,raw,box,previous,previous_box)))
                previous,previous_box=raw,box
                if len(jobs) >= 8:
                    write_one()
            while jobs:
                write_one()
            index['animations'][name]={'frames':frames}
            print(f'{name}: {len(frames)} frames, cumulative {packed.tell()/1024**2:.1f} MiB',flush=True)
    index['data_bytes']=temporary.stat().st_size
    temporary.replace(output/'pet-frames.bin')
    (output/'pet-frames.json').write_text(json.dumps(index,separators=(',',':'))+'\n',encoding='utf-8')
    manifest['version']=7
    manifest['playback_pack']='pet-frames.json'
    manifest['runtime_codec']=index['codec']
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Lossless compact pack complete: {index["data_bytes"]/1024**2:.1f} MiB',flush=True)
    return output


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    build(output=args.output.resolve() if args.output else None)
