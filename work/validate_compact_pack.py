"""Compare every compact frame with the previous lossless playback pack."""
import argparse
import json
from pathlib import Path
import sys
import zlib

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from PIL import Image
from frame_stream import FrameArchive,pack_frame

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--candidate',type=Path,default=ROOT/'work/repaired-assets/pet-frames.json')
args=parser.parse_args()
manifest=json.loads((ROOT/'assets/manifest.json').read_text(encoding='utf-8'))
compact=FrameArchive(args.candidate)
report={}
for name,animation in compact.animations.items():
    if name in manifest['animations']:
        source=Image.open(ROOT/'assets'/manifest['animations'][name]['file'])
        count=source.n_frames
        def native(number):
            source.seek(number)
            rgba=source.convert('RGBA');box=rgba.getbbox()
            return (rgba.crop(box).tobytes(),box),int(source.info['duration'])
        def reference(number,size):
            source.seek(number)
            return pack_frame(source.convert('RGBA').resize(size,Image.Resampling.LANCZOS))
    else:
        original=FrameArchive(ROOT/'assets'/name/'pet-frames.json')
        count=len(original.animations[name]['frames'])
        source=original.sources[name].open('rb')
        def native(number):
            frame=original.animations[name]['frames'][number]
            offset,length,*box=frame['native']
            source.seek(offset)
            return (zlib.decompress(source.read(length)),tuple(box)),frame['ms']
        def reference(number,size):
            if size == original.display_canvas:
                return original.read(name,number,size)
            (pixels,box),_=native(number)
            rgba=Image.new('RGBA',original.canvas)
            rgba.paste(Image.frombytes('RGBA',(box[2]-box[0],box[3]-box[1]),pixels),box[:2])
            return pack_frame(rgba.resize(size,Image.Resampling.LANCZOS))
    assert count == len(animation['frames'])
    other_sizes=0
    with source:
        for number,frame in enumerate(animation['frames']):
            expected,ms=native(number)
            assert ms == frame['ms']
            assert compact._native(name,number) == expected,(name,number,'native')
            assert compact.read(name,number,(560,480)) == reference(number,(560,480)),(name,number,'default')
            if number % 97 == 0 or number == count-1:
                for size in ((336,288),(392,336),(728,624),(840,720)):
                    assert compact.read(name,number,size) == reference(number,size),(name,number,size)
                    other_sizes += 1
        for number in (count-1,0,count//2,3):
            assert compact.read(name,number,(336,288)) == reference(number,(336,288))
    report[name]={'native_and_default_frames_compared':count,'pixel_differences':0,
                  'additional_sizes_compared':other_sizes,'random_seeks_compared':4}
    print(name,json.dumps(report[name]),flush=True)
assert compact.peak_raw_cache_bytes <= 16*1024**2
assert compact.loop_cache.peak_bytes <= 8*1024**2
result={'animations':report,'all_native_pixels_alpha_offsets_and_timings_identical':True,
        'native_cache_peak_bytes':compact.peak_raw_cache_bytes,
        'standing_loop_cache_peak_bytes':compact.loop_cache.peak_bytes,
        'compact_pack_bytes':compact.path.stat().st_size}
(ROOT/'work/compact-quality-validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print('Every compact frame is pixel-identical.',flush=True)
