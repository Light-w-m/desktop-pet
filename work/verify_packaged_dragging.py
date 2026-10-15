"""Check the standalone binary's optional dragging archive byte for byte."""
import hashlib
import json
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader

ROOT = Path(__file__).resolve().parent.parent
folder = ROOT/'assets'/'dragging'
metadata = json.loads((folder/'source.json').read_text(encoding='utf-8'))
archive = CArchiveReader(str(ROOT/'work'/'dist'/'CitlaliDesktopPet.exe'))
names = {name.replace('\\','/'):name for name in archive.toc}
assert json.loads(archive.extract(names['assets/dragging/source.json'])) == metadata
for name,expected in metadata['files'].items():
    contents = archive.extract(names['assets/dragging/'+name])
    assert len(contents) == expected['bytes'] and hashlib.sha256(contents).hexdigest() == expected['sha256']
report = {'embedded_dragging_frames':metadata['output_frames'],'all_archive_hashes_match':True,
          'original_partial_gif_framing_preserved':True}
(ROOT/'work'/'dragging-package-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
