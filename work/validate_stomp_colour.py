"""Compare the rendered stomp palette with the actual standing asset."""
import argparse
import json
from pathlib import Path
import sys
import zlib

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'work/sources/drag-deps'))
import cv2
import numpy as np
from PIL import Image,ImageDraw


def native(folder,number=-1):
    index=json.loads((folder/'pet-frames.json').read_text(encoding='utf-8'))
    frame=index['animations']['stomping']['frames'][number]
    offset,length,*box=frame['native']
    with (folder/index['data']).open('rb') as source:
        source.seek(offset);pixels=zlib.decompress(source.read(length))
    image=Image.new('RGBA',tuple(index['canvas']))
    image.paste(Image.frombytes('RGBA',(box[2]-box[0],box[3]-box[1]),pixels),box[:2])
    return image


def statistics(image):
    pixels=np.asarray(image)
    core=cv2.erode((pixels[:,:,3] > 240).astype('uint8'),np.ones((3,3),'uint8')) > 0
    rgb=pixels[:,:,:3][core].astype('float32')
    return {'rgb_mean':rgb.mean(axis=0).tolist(),'rgb_median':np.median(rgb,axis=0).tolist(),
        'luminance_mean':float((rgb @ np.array([.2126,.7152,.0722])).mean()),
        'opaque_pixels':int(core.sum())}


parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--previous-pack',type=Path,default=ROOT/'backups/before-stomp-recovery-20261016/stomping')
args=parser.parse_args()
reference=Image.open(ROOT/'assets/standing-obs.webp').convert('RGBA')
before=native(args.previous_pack) if (args.previous_pack/'pet-frames.json').is_file() else None
after=native(ROOT/'assets/stomping')
reference_stats,after_stats=map(statistics,(reference,after))
before_stats=statistics(before) if before is not None else None
old_error=abs(before_stats['luminance_mean']-reference_stats['luminance_mean']) if before_stats else None
new_error=abs(after_stats['luminance_mean']-reference_stats['luminance_mean'])
assert new_error < 10,new_error
median_error=float(np.abs(np.array(after_stats['rgb_median'])-reference_stats['rgb_median']).mean())
assert median_error < 14,median_error
metadata=json.loads((ROOT/'assets/stomping/source.json').read_text(encoding='utf-8'))
assert metadata['sequence'] == ['stomp','settle_to_standing']
assert metadata['discarded_intro_frames'] == 63 and metadata['output_frames'] >= 294
assert metadata['colour_match']['fixed_palette_anchors'] and metadata['colour_match']['pose_independent']
assert metadata['recovery']['source_ending_retained']
reference_mask=np.asarray(reference)[:,:,3] > 128
ending_mask=np.asarray(after)[:,:,3] > 128
overlap=float(np.sum(reference_mask & ending_mask)/np.sum(reference_mask | ending_mask))
def extent(mask):
    y,x=np.where(mask)
    return [int(x.min()),int(y.min()),int(x.max()+1),int(y.max()+1)]
reference_box,ending_box=extent(reference_mask),extent(ending_mask)
assert overlap > .82,('Final pose is not the normal frontal stance',overlap)
assert max(abs(ending_box[i]-reference_box[i]) for i in (1,3)) <= 6,('Head/soles jump on return',reference_box,ending_box)
report={'standing':reference_stats,'old_stomp':before_stats,'new_stomp':after_stats,
    'old_luminance_error':old_error,'new_luminance_error':new_error,
    'new_rgb_median_error':median_error,'two_hand_intro_removed':True,
    'fixed_palette_anchors_and_background_exposure_tracking':True,
    'complete_source_ending_retained':True,'source_range_seconds':metadata['source_range_seconds'],
    'ending_standing_silhouette_iou':overlap,'reference_bbox':reference_box,'ending_bbox':ending_box}
(ROOT/'work/stomp-colour-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
panels=[('Standing reference',reference)]+([('Previous truncated ending',before)] if before is not None else [])+[('Complete recovered ending',after)]
preview=Image.new('RGB',(len(panels)*420,380),'#e9e3e7');draw=ImageDraw.Draw(preview)
for i,(title,image) in enumerate(panels):
    bg=Image.new('RGBA',image.size,'#e9e3e7');bg.alpha_composite(image)
    preview.paste(bg.resize((420,360)),(i*420,20));draw.text((i*420+12,4),title,fill='#594457')
preview.save(ROOT/'work/stomping-tone-comparison.jpg')
print(json.dumps(report,indent=2),flush=True)
