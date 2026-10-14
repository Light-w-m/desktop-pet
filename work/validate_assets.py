from pathlib import Path
import json
import numpy as np
from PIL import Image,ImageSequence

root=Path(__file__).resolve().parent/'repaired-assets'
manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
report={}
for name,spec in manifest['animations'].items():
    durations=[];changes=[];first=previous=None;count=0
    with Image.open(root/spec['file']) as im:
        for frame in ImageSequence.Iterator(im):
            a=np.array(frame.convert('RGBA'))
            assert frame.size==tuple(manifest['canvas'])
            assert a[:,:,3].max()>128
            assert int((a[:,:,3]>128).sum())>=2000,'Missing character: '+name+' frame '+str(count)
            assert max(a[:6,:,3].max(),a[-6:,:,3].max(),a[:,:6,3].max(),a[:,-6:,3].max())==0
            visible=a[:,:,:3].astype('float32')*(a[:,:,3:4].astype('float32')/255)
            if first is None:first=visible.copy()
            if previous is not None:changes.append(float(np.abs(visible-previous).mean()))
            previous=visible
            count+=1
            durations.append(im.info['duration'])
    assert count==spec['frames']
    assert sum(durations)==spec['duration_ms']
    assert set(durations)<={16,17}
    # Compare visual (premultiplied) pixels rather than hidden transparent RGB.
    seam=float(np.abs(previous-first).mean())
    assert seam<=max(changes)*1.15
    report[name]={'frames':count,'duration_ms':sum(durations),'fps':count*1000/sum(durations),'seam_difference':seam,'max_frame_difference':max(changes),'median_frame_difference':float(np.median(changes))}
    print(name,report[name])
(root.parent/'asset-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
