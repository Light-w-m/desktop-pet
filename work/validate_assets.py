from pathlib import Path
import json
import numpy as np
from PIL import Image,ImageSequence

root=Path(__file__).resolve().parent/'repaired-assets'
manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
report={}
canonical=None
for name,spec in manifest['animations'].items():
    durations=[];changes=[];first=previous=None;count=0;first_rgba=None
    with Image.open(root/spec['file']) as im:
        for frame in ImageSequence.Iterator(im):
            a=np.array(frame.convert('RGBA'))
            a[a[:,:,3]==0,:3]=0
            assert frame.size==tuple(manifest['canvas'])
            assert a[:,:,3].max()>128
            assert int((a[:,:,3]>128).sum())>=2000,'Missing character: '+name+' frame '+str(count)
            if manifest['version']>=4 and name=='drinking' and count==833:
                assert int((a[485:590,343:525,3]>128).sum())>4000,'Detached shrinking cushion was lost'
            if manifest['version']>=4 and name=='reading' and count==676:
                assert int((a[300:470,550:755,3]>128).sum())>6000,'Sideways shrinking cushion was lost'
            assert max(a[:6,:,3].max(),a[-6:,:,3].max(),a[:,:6,3].max(),a[:,-6:,3].max())==0,'Touches canvas border: '+name+' frame '+str(count)
            visible=a[:,:,:3].astype('float32')*(a[:,:,3:4].astype('float32')/255)
            if first is None:first=visible.copy()
            if first_rgba is None:first_rgba=a.copy()
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
    if manifest['version']>=4:
        assert spec['lossless'] and spec['native_frames']
        assert np.array_equal(first_rgba,a),'Different standing endpoints: '+name
        if canonical is None:canonical=first_rgba
        assert np.array_equal(canonical,first_rgba),'Different action switch boundary: '+name
    report[name]={'frames':count,'duration_ms':sum(durations),'fps':count*1000/sum(durations),'seam_difference':seam,'max_frame_difference':max(changes),'median_frame_difference':float(np.median(changes))}
    if manifest['version']>=4:report[name]['shared_standing_boundary']=True
    print(name,report[name])
(root.parent/'asset-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
