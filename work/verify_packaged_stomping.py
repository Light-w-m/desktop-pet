"""Verify embedded hidden assets and run the actual EXE's one-shot media path."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

from PyInstaller.archive.readers import CArchiveReader
from verify_embedded_motion import verify_motion

ROOT = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--exe', type=Path, default=ROOT/'work'/'dist'/'CitlaliDesktopPet.exe')
args = parser.parse_args()
executable = args.exe.resolve()
archive = CArchiveReader(str(executable))
names = {name.replace('\\', '/'): name for name in archive.toc}
metadata = json.loads((ROOT/'assets'/'stomping'/'source.json').read_text(encoding='utf-8'))
verify_motion(archive,names,'stomping')
sticker = ROOT/'assets'/'easter-eggs'/'shake-angry.png'
assert archive.extract(names['assets/easter-eggs/shake-angry.png']) == sticker.read_bytes()
assert sum(name.startswith('assets/expressions/') and name.endswith('.png') for name in names) == 9
samples=[]
for scale in (.6,1.0,1.3):
    subprocess.run([str(executable), '--qa-seconds', '5', '--qa-stomp', '--qa-scale', str(scale)],
                   cwd=executable.parent, check=True, timeout=90)
    raw = json.loads((executable.parent/'work'/'stomp-playback-qa.json').read_text(encoding='utf-8'))
    draws=raw['draws']
    positions=[i for i,row in enumerate(draws) if row[0] == 'stomping']
    stomps=[draws[i] for i in positions]
    assert len(stomps) >= 50, f'Too few rendered stomp frames: {len(stomps)}'
    duration = stomps[-1][2]-stomps[0][2]
    assert .85 < duration < 1.2
    assert draws[positions[0]-1][0] == 'dragging', 'Did not exercise the real outgoing drag animation'
    assert draws[-1][0] == 'standing', 'Executable did not recover the main action'
    assert raw['peak_cache_frames'] <= 12 and raw['peak_cache_bytes'] <= 24*1024**2
    indices = [row[1] for row in stomps]
    assert all(a <= b for a,b in zip(indices,indices[1:])), 'Stomp unexpectedly looped'
    unique = [row for i,row in enumerate(stomps) if i == 0 or row[1] != stomps[i-1][1]]
    assert len(unique) >= 50, 'Too many dropped media frames'
    entry_gap=1000*(draws[positions[0]][2]-draws[positions[0]-1][2])
    exit_gap=1000*(draws[positions[-1]+1][2]-draws[positions[-1]][2])
    entry_ms=raw['render_ms'][positions[0]]
    exit_ms=raw['render_ms'][positions[-1]+1]
    assert max(entry_gap,exit_gap) < 75, 'Animation stalled at a transition boundary'
    assert max(entry_ms,exit_ms) < 35, 'Transition waited for a cold frame decode'
    states=[row for row in raw['reaction_states'] if row['pose'] == 'stomping']
    assert sum(0 < row['elapsed'] < .2 for row in states) >= 8, 'Intro fade was skipped'
    exit_states=[row for row in states if row['elapsed'] > .76]
    assert len(exit_states) >= 10
    assert exit_states[-1]['main_position']-exit_states[0]['main_position'] > .15, 'Return action froze during the fade'
    samples.append({'scale':scale,'rendered_stomp_frames':len(unique),
        'rendered_fps':(len(unique)-1)/duration,'visible_duration_seconds':duration,
        'entry_frame_gap_ms':entry_gap,'exit_frame_gap_ms':exit_gap,
        'entry_render_ms':entry_ms,'exit_render_ms':exit_ms,
        'cache_peak_bytes':raw['peak_cache_bytes'],'cache_peak_frames':raw['peak_cache_frames']})
report = {'embedded_pack_checksums': True, 'hidden_sticker_embedded': True, 'normal_picker_still_nine': True,
          'actual_exe_one_shot_and_resume':True,'outgoing_drag_and_live_return':True,
          'intro_and_outro_frames_not_skipped':True,'samples':samples}
(ROOT/'work'/'stomp-package-validation.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
print(json.dumps(report, indent=2), flush=True)
