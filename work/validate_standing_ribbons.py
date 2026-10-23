"""Check decoded fabric colours, unchanged surrounding pixels and media timing."""
import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parent.parent
LOCAL=ROOT/'local-media/standing-ribbon-fix-20261023'
BACKUP=ROOT/'backups/before-gait-ribbon-fix-20261023/assets'
regions=json.loads((LOCAL/'repair.json').read_text())['native_regions']
manifest=json.loads((ROOT/'assets/manifest.json').read_text(encoding='utf-8'))
outside=np.ones((720,840),bool)
for x,y,X,Y in regions:outside[y:Y,x:X]=False
colours={'before':[],'after':[]};checked={}
for name,spec in manifest['animations'].items():
    with Image.open(BACKUP/spec['file']) as before,Image.open(ROOT/'assets'/spec['file']) as after:
        assert before.n_frames==after.n_frames==spec['frames']
        for i in range(after.n_frames):
            before.seek(i);after.seek(i)
            a=np.asarray(before.convert('RGBA'));b=np.asarray(after.convert('RGBA'))
            assert before.info['duration']==after.info['duration'],(name,i,'timing')
            # RGB under alpha zero is unspecified in animated WebP. Compare
            # every visible pixel plus alpha, including all untouched frames.
            unchanged=outside if name=='standing' or i<12 or i>=after.n_frames-12 else np.ones(outside.shape,bool)
            assert np.array_equal(a[:,:,3][unchanged],b[:,:,3][unchanged]),(name,i,'alpha outside repair')
            visible=unchanged&(a[:,:,3]>0)
            assert np.array_equal(a[:,:,:3][visible],b[:,:,:3][visible]),(name,i,'RGB outside repair')
            if name=='standing':
                for label,pixels in (('before',a),('after',b)):
                    counts=[]
                    for x,y,X,Y in ((310,462,398,509),(518,462,598,509)):
                        r,g,blue,alpha=np.moveaxis(pixels[y:Y,x:X].astype('int16'),2,0)
                        cyan=(g>r+10)&(blue>r+20)&(alpha>80)
                        pink=(r>g+12)&(blue>g+6)&(r>100)&(alpha>128)
                        counts.append({'cyan':int(cyan.sum()),'pink':int(pink.sum())})
                    colours[label].append(counts)
        checked[name]=after.n_frames
summary={}
for label,frames in colours.items():
    summary[label]={'maximum_cyan_pixels':[max(f[i]['cyan'] for f in frames) for i in (0,1)],
                    'minimum_pink_pixels':[min(f[i]['pink'] for f in frames) for i in (0,1)]}
assert summary['after']['maximum_cyan_pixels']==[0,0]
assert min(summary['after']['minimum_pink_pixels'])>200,'A pink costume tail disappeared'
report={'standing_frames_checked':153,'all_main_frames_checked':checked,
        'costume_tail_colours':summary,'unchanged_visible_pixels_outside_repair':True,
        'unchanged_alpha_outside_repair':True,'unchanged_timings':True,'regions':regions}
(ROOT/'work/standing-ribbon-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2),flush=True)
