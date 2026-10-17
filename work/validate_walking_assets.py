"""Check complete framing, alpha, cadence and periodic walk seams."""
import hashlib
import json
from pathlib import Path
import statistics
import sys
import zlib

from PIL import Image,ImageChops,ImageStat

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from frame_stream import FrameArchive

folder=ROOT/'assets/walking'
metadata=json.loads((folder/'source.json').read_text(encoding='utf-8'))
for name,expected in metadata['files'].items():
    data=(folder/name).read_bytes()
    assert len(data)==expected['bytes'] and hashlib.sha256(data).hexdigest()==expected['sha256']
archive=FrameArchive(folder/'pet-frames.json')
report={};previews=[]
for direction,detail in metadata['directions'].items():
    name='walking_'+direction;animation=archive.animations[name];frames=[]
    assert len(animation['frames'])==detail['output_frames']
    assert sum(f['ms'] for f in animation['frames'])==detail['duration_ms']
    margins=[]
    for i,record in enumerate(animation['frames']):
        tile=archive.read(name,i,(560,480))
        raw=tile['pixels'];x,y=tile['offset'];w,h=tile['size']
        margins.append(min(x,y,560-x-w,480-y-h))
        assert margins[-1]>=6,(name,i,'cropped')
        assert all(raw[c]<=raw[c-c%4+3] for c in range(len(raw)) if c%4!=3)
        image=Image.new('RGBA',(560,480))
        image.paste(Image.frombytes('RGBA',(w,h),raw,'raw','BGRA'),(x,y))
        frames.append(image)
    def difference(a,b):return sum(ImageStat.Stat(ImageChops.difference(a,b)).mean)/4
    deltas=[difference(a,b) for a,b in zip(frames,frames[1:])]
    seam=difference(frames[-1],frames[0]);p95=statistics.quantiles(deltas,n=20)[18]
    assert seam<max(1.5,p95*2),(name,seam,p95)
    report[direction]={'frames':len(frames),'duration_ms':detail['duration_ms'],'minimum_canvas_margin_px':min(margins),
        'seam_mean_channel_difference':seam,'p95_neighbor_difference':p95,'valid_premultiplied_alpha':True}
    previews.extend(frames[i] for i in (0,len(frames)//4,len(frames)//2,3*len(frames)//4))
sheet=Image.new('RGBA',(1120,480),'#d8cbd5')
for i,frame in enumerate(previews):
    # Frames contain premultiplied pixels; restore straight colour for preview.
    tile=frame.copy();channels=tile.split();alpha=channels[3]
    rgb=bytearray(tile.tobytes())
    for j in range(0,len(rgb),4):
        if rgb[j+3]:
            for c in range(3):rgb[j+c]=min(255,round(rgb[j+c]*255/rgb[j+3]))
    sheet.alpha_composite(Image.frombytes('RGBA',tile.size,bytes(rgb)).resize((280,240)),(i%4*280,i//4*240))
sheet.convert('RGB').save(ROOT/'work/walking-validated-contact.jpg')
(ROOT/'work/walking-asset-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2),flush=True)
