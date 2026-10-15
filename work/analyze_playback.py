"""Check actual packaged playback cadence and recorded action boundaries."""
from pathlib import Path
import json
import statistics

root=Path(__file__).resolve().parent
qa_path=root/'dist'/'work'/'playback-qa.json'
assert qa_path.stat().st_mtime >= (root/'dist'/'CitlaliDesktopPet.exe').stat().st_mtime,'QA predates the executable'
qa=json.loads(qa_path.read_text(encoding='utf-8'))
assert 'peak_cache_frames' in qa,'Expected the bounded streaming player'
report={}
for name in ['standing','drinking','reading']:
    draws=[entry for entry in qa['draws'] if entry[0]==name]
    assert len(draws)>400,'Packaged action was not exercised: '+name
    gaps=[(b[2]-a[2])*1000 for a,b in zip(draws,draws[1:])]
    fps=(len(draws)-1)/(draws[-1][2]-draws[0][2])
    p95=sorted(gaps)[int((len(gaps)-1)*.95)]
    assert fps>57,'Playback misses too many native frames: '+name
    assert p95<27,'Uneven playback: '+name
    report[name]={'fps':fps,'p95_frame_ms':p95,'frames_drawn':len(draws)}
names=[entry[0] for entry in qa['draws']]
switches=[(a,b) for a,b in zip(qa['draws'],qa['draws'][1:]) if a[0]!=b[0]]
manifest=json.loads((root/'repaired-assets'/'manifest.json').read_text(encoding='utf-8'))
for before,after in switches:
    assert before[1]>=manifest['animations'][before[0]]['frames']-3,'Cut a pose before its standing return'
    assert after[1]<=1,'New pose did not start at the common standing boundary'
report['verified_switches']=[{'from':a[0],'to':b[0],'last_frame':a[1],'first_frame':b[1]} for a,b in switches]
report['render_mean_ms']=statistics.mean(qa['render_ms'])
assert qa.get('peak_cache_frames',0)<=12,'Decoded cache exceeded its frame bound'
assert qa.get('peak_cache_bytes',0)<=24*1024*1024,'Decoded cache exceeded its memory bound'
report['peak_cache_frames']=qa.get('peak_cache_frames')
report['peak_cache_mib']=qa.get('peak_cache_bytes',0)/(1024*1024)
(root/'exe-playback-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
