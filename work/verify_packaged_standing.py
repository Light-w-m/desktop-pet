"""Check the repaired embedded idle and several real cold/warm loop cycles."""
import hashlib
import json
from pathlib import Path
import statistics
import subprocess

from PyInstaller.archive.readers import CArchiveReader

ROOT=Path(__file__).resolve().parent.parent
exe=ROOT/'work/dist/CitlaliDesktopPet.exe'
archive=CArchiveReader(str(exe));names={n.replace('\\','/'):n for n in archive.toc}
pack=json.loads(archive.extract(names['assets/pet-frames.json']))
checksums=json.loads((ROOT/'assets/source-checksums.json').read_text())['files']
for name,expected in checksums.items():assert pack['source_files']['assets/'+name]==expected
assert len(pack['animations']['standing']['frames'])==153
samples=[]
for scale in (1,1.3):
    subprocess.run([str(exe),'--qa-seconds','13','--qa-standing','--qa-scale',str(scale)],
                   cwd=exe.parent,check=True,timeout=45)
    raw=json.loads((exe.parent/'work/standing-playback-qa.json').read_text())
    draws=raw['draws'];assert {r[0] for r in draws}=={'standing'}
    gaps=[(b[2]-a[2])*1000 for a,b in zip(draws,draws[1:])]
    loops=[(b[2]-a[2])*1000 for a,b in zip(draws,draws[1:]) if b[1]<a[1]]
    fps=(len(draws)-1)/(draws[-1][2]-draws[0][2]);p95=statistics.quantiles(gaps,n=20)[18]
    assert fps>58.5 and p95<27,(scale,fps,p95)
    assert len(loops)>=4 and max(loops)<45,(scale,loops)
    assert max(gaps)<75,(scale,max(gaps))
    assert raw['peak_cache_frames']<=12 and raw['peak_cache_bytes']<=24*1024**2
    assert raw['native_cache_peak_bytes']<=16*1024**2 and raw['loop_cache_peak_bytes']<=8*1024**2
    samples.append({'scale':scale,'rendered_fps':fps,'p95_frame_ms':p95,'max_frame_ms':max(gaps),
                    'loop_boundary_gaps_ms':loops,'cache_peak_bytes':raw['peak_cache_bytes'],
                    'loop_cache_peak_bytes':raw['loop_cache_peak_bytes']})
report={'embedded_repaired_assets_match':True,'costume_colour_validation':'standing-ribbon-validation.json',
        'all_cold_and_warm_loops_smooth':True,'samples':samples}
(ROOT/'work/standing-package-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2),flush=True)
