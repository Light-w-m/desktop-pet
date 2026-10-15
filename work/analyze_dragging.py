"""Validate the standalone executable's multiple dragging loops and return."""
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parent.parent
path = ROOT/'work'/'dist'/'work'/'drag-playback-qa.json'
assert path.stat().st_mtime >= (ROOT/'work'/'dist'/'CitlaliDesktopPet.exe').stat().st_mtime
data = json.loads(path.read_text())
all_draws = [row for row in data['draws'] if row[0] == 'dragging']
draws = [row for i,row in enumerate(all_draws) if not i or row[1] != all_draws[i-1][1]]
assert len(draws) > 450
gaps = [(b[2]-a[2])*1000 for a,b in zip(draws,draws[1:])]
fps = (len(draws)-1)/(draws[-1][2]-draws[0][2])
p95 = sorted(gaps)[int(.95*(len(gaps)-1))]
loops = sum(b[1] < a[1] for a,b in zip(draws,draws[1:]))
assert fps > 57 and p95 < 27 and loops >= 2
assert data['draws'][0][0] == data['draws'][-1][0] == 'standing'
assert data['peak_cache_frames'] <= 12 and data['peak_cache_bytes'] <= 24*1024**2
report = dict(fps=fps,p95_frame_ms=p95,frames_drawn=len(draws),complete_loops=loops,
              returns_to_previous_action=True,render_mean_ms=statistics.mean(data['render_ms']),
              peak_cache_frames=data['peak_cache_frames'],peak_cache_mib=data['peak_cache_bytes']/1024**2)
(ROOT/'work'/'exe-dragging-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
