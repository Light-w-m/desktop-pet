"""Verify embedded hidden assets and run the actual EXE's one-shot media path."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

from PyInstaller.archive.readers import CArchiveReader

ROOT = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--exe', type=Path, default=ROOT/'work'/'dist'/'CitlaliDesktopPet.exe')
args = parser.parse_args()
executable = args.exe.resolve()
archive = CArchiveReader(str(executable))
names = {name.replace('\\', '/'): name for name in archive.toc}
metadata = json.loads((ROOT/'assets'/'stomping'/'source.json').read_text(encoding='utf-8'))
assert json.loads(archive.extract(names['assets/stomping/source.json'])) == metadata
for name, expected in metadata['files'].items():
    contents = archive.extract(names['assets/stomping/'+name])
    assert len(contents) == expected['bytes'] and hashlib.sha256(contents).hexdigest() == expected['sha256']
sticker = ROOT/'assets'/'easter-eggs'/'shake-angry.png'
assert archive.extract(names['assets/easter-eggs/shake-angry.png']) == sticker.read_bytes()
assert sum(name.startswith('assets/expressions/') and name.endswith('.png') for name in names) == 9
subprocess.run([str(executable), '--qa-seconds', '8', '--qa-stomp'], cwd=executable.parent, check=True, timeout=90)
raw = json.loads((executable.parent/'work'/'stomp-playback-qa.json').read_text(encoding='utf-8'))
stomps = [row for row in raw['draws'] if row[0] == 'stomping']
assert len(stomps) >= 50, f'Too few rendered stomp frames: {len(stomps)}'
duration = stomps[-1][2]-stomps[0][2]
assert .85 < duration < 1.2
assert raw['draws'][-1][0] == 'standing', 'Executable did not recover the main action'
assert raw['peak_cache_frames'] <= 12 and raw['peak_cache_bytes'] <= 24*1024**2
indices = [row[1] for row in stomps]
assert all(a <= b for a, b in zip(indices, indices[1:])), 'Stomp unexpectedly looped'
unique = [row for i, row in enumerate(stomps) if i == 0 or row[1] != stomps[i-1][1]]
assert len(unique) >= 50, 'Too many dropped media frames'
report = {'embedded_pack_checksums': True, 'hidden_sticker_embedded': True, 'normal_picker_still_nine': True,
          'actual_exe_one_shot_and_resume': True, 'rendered_stomp_frames': len(unique),
          'rendered_updates_including_fades': len(stomps),
          'rendered_fps': (len(unique)-1)/duration, 'visible_duration_seconds': duration,
          'cache_peak_bytes': raw['peak_cache_bytes'], 'cache_peak_frames': raw['peak_cache_frames']}
(ROOT/'work'/'stomp-package-validation.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
print(json.dumps(report, indent=2), flush=True)
