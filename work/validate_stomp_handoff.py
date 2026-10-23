"""Verify transparent foot separation, intact boots and the exact idle endpoint."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'work/sources/drag-deps'))
import cv2
import numpy as np
from PIL import Image
from citlali_pet.animation.frame_stream import FrameArchive,pack_frame
from repair_stomp_handoff import native

before=ROOT/'backups/before-stomp-handoff-fix-20261023/assets/stomping'
after=ROOT/'assets/stomping'
aindex=json.loads((before/'pet-frames.json').read_text());bindex=json.loads((after/'pet-frames.json').read_text())
ar=aindex['animations']['stomping']['frames'];br=bindex['animations']['stomping']['frames']
assert len(ar)==len(br)==296
outside=np.ones((720,840),bool);outside[595:688,350:570]=False
before_probe=after_probe=0;gap_checks=0;prev=None;tail_steps=[]
with (before/aindex['data']).open('rb') as af,(after/bindex['data']).open('rb') as bf:
    for i,(ra,rb) in enumerate(zip(ar,br)):
        a,b=native(af,ra['native']),native(bf,rb['native'])
        assert ra['ms']==rb['ms']
        if i<260:
            assert np.array_equal(a[outside],b[outside]),(i,'Pixels outside the foot gap changed')
            bright=(a[595:688,350:570,:3].min(axis=2)>100)&(a[595:688,350:570,:3].max(axis=2)>155)&(a[595:688,350:570,3]>180)
            assert np.array_equal(a[595:688,350:570][bright],b[595:688,350:570][bright]),(i,'Boot fabric changed')
        if 170<=i<=209:
            before_probe+=int((a[650:667,456:470,3]>128).sum())
            after_probe+=int((b[650:667,456:470,3]>128).sum())
            # Both soles must be separate connected shapes in the lower band.
            mask=(b[600:688,350:570,3]>128).astype('uint8')
            count,labels,stats,centres=cv2.connectedComponentsWithStats(mask,8)
            boots=[k for k in range(1,count) if stats[k,cv2.CC_STAT_AREA]>300]
            assert len(boots)==2,(i,'The floor still connects the soles',len(boots))
            gap_checks+=1
        if i>=260:
            p=b.astype('float32');p[:,:,:3]*=p[:,:,3:4]/255
            if prev is not None:tail_steps.append(float(np.abs(p-prev).mean()))
            prev=p
    target=Image.open(ROOT/'assets/standing-obs.webp').convert('RGBA')
    assert np.array_equal(b,np.asarray(target)),'Last frame differs from current idle'
assert before_probe>5000 and after_probe==0,(before_probe,after_probe)
assert max(tail_steps[-8:])<.5,tail_steps[-8:]
archive=FrameArchive(after/'pet-frames.json')
sizes=((336,288),(560,480),(728,624),(840,720))
for size in sizes:
    assert archive.read('stomping',295,size)==pack_frame(target.resize(size,Image.Resampling.LANCZOS)),size
report={'frames_and_timings_preserved':296,'separate_boots_checked':gap_checks,
        'dark_gap_probe_before':before_probe,'dark_gap_probe_after':after_probe,
        'body_outside_gap_unchanged_before_handoff':True,'boot_fabric_preserved':True,
        'endpoint_exactly_matches_current_idle_at_sizes':[list(s) for s in sizes],
        'handoff_frames':36,'last_eight_frame_changes_premultiplied_mae':tail_steps[-8:]}
(ROOT/'work/stomp-handoff-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2),flush=True)
