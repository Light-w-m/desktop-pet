"""Validate embedded walk loops and exercise the frozen renderer's bounces."""
import hashlib
import json
from pathlib import Path
import statistics
import subprocess

from PyInstaller.archive.readers import CArchiveReader

ROOT=Path(__file__).resolve().parent.parent
exe=ROOT/'work/dist/CitlaliDesktopPet.exe'
archive=CArchiveReader(str(exe));names={n.replace('\\','/'):n for n in archive.toc}
metadata=json.loads((ROOT/'assets/walking/source.json').read_text(encoding='utf-8'))
assert json.loads(archive.extract(names['assets/walking/source.json'])) == metadata
pack=json.loads(archive.extract(names['assets/pet-frames.json']))
data=archive.extract(names['assets/'+pack['data']])
assert hashlib.sha256(data).hexdigest() == hashlib.sha256((ROOT/'work/repaired-assets'/pack['data']).read_bytes()).hexdigest()
del data
assert {n for n in pack['animations'] if n.startswith('walking_')} == {'walking_left','walking_right'}
for direction in ('left','right'):
    detail=metadata['directions'][direction]
    frames=pack['animations']['walking_'+direction]['frames']
    assert len(frames) == detail['output_frames']
    assert sum(f['ms'] for f in frames) == detail['duration_ms']
    assert all(f['base'] is None for f in frames)
for name,expected in metadata['files'].items():
    assert pack['source_files']['assets/walking/'+name] == expected
samples=[]
for scale in (.7,1.3):
    subprocess.run([str(exe),'--qa-seconds','16','--qa-walk','--qa-scale',str(scale)],
                   cwd=exe.parent,check=True,timeout=55)
    raw=json.loads((exe.parent/'work/walk-playback-qa.json').read_text(encoding='utf-8'))
    draws=raw['draws'];walking=[r for r in draws if r[0].startswith('walking_')]
    unique=[r for i,r in enumerate(walking) if i==0 or r[:2]!=walking[i-1][:2]]
    states=raw['walking_states'];active=[r for r in states if r['active']]
    assert {r['direction'] for r in active} == {-1,1}
    assert {r[0] for r in walking} == {'walking_left','walking_right'}
    assert len({r['y'] for r in states}) == 1,'Vertical line drifted'
    assert all(r['left']-.5 <= r['x'] <= r['right']+.5 for r in active)
    stopped=[r for r in states if not r['active']]
    assert stopped and len({r['x'] for r in stopped}) == 1
    assert draws[-1][0] == 'standing'
    assert raw['peak_cache_frames'] <= 12 and raw['peak_cache_bytes'] <= 24*1024**2
    assert raw['native_cache_peak_bytes'] <= 16*1024**2 and raw['loop_cache_peak_bytes'] <= 8*1024**2
    fps=(len(unique)-1)/(unique[-1][2]-unique[0][2])
    positions=[i for i,r in enumerate(draws) if r[0].startswith('walking_')]
    entry_gap=(draws[positions[0]][2]-draws[positions[0]-1][2])*1000
    exit_gap=(draws[positions[-1]+1][2]-draws[positions[-1]][2])*1000
    assert max(entry_gap,exit_gap)<75
    gaps=[(b[2]-a[2])*1000 for a,b in zip(walking,walking[1:])]
    reversals=[(b[2]-a[2])*1000 for a,b in zip(walking,walking[1:]) if a[0]!=b[0]]
    assert fps > 58.5,(scale,fps)
    assert reversals and max(reversals) < 45,(scale,reversals)
    samples.append({'scale':scale,'rendered_fps':fps,'p95_frame_gap_ms':statistics.quantiles(gaps,n=20)[18],
        'entry_frame_gap_ms':entry_gap,'exit_frame_gap_ms':exit_gap,
        'direction_switch_gaps_ms':reversals,'cache_peak_bytes':raw['peak_cache_bytes'],'cache_peak_frames':raw['peak_cache_frames']})
report={'embedded_checksums_match':True,'horizontal_line_constant':True,'automatic_edge_reversal':True,
    'immediate_direction_switch':True,'turn_animation_included':False,
    'interrupted_motion_stays_stopped':True,'frames':{d:metadata['directions'][d]['output_frames'] for d in ('left','right')},
    'samples':samples}
(ROOT/'work/walking-package-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2),flush=True)
