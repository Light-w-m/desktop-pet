"""Verify that every transparent sticker is embedded verbatim in the EXE."""
import hashlib
import json
from pathlib import Path
import sys

from PyInstaller.archive.readers import CArchiveReader

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from expressions import EXPRESSIONS

archive = CArchiveReader(str(ROOT/'work'/'dist'/'CitlaliDesktopPet.exe'))
names = {name.replace('\\', '/'): name for name in archive.toc}
report = {}
for key, label in EXPRESSIONS:
    name = f'assets/expressions/{key}.png'
    source = (ROOT/name).read_bytes()
    embedded = archive.extract(names[name])
    assert embedded == source, 'Embedded expression differs: '+key
    report[key] = {'bytes': len(embedded), 'sha256': hashlib.sha256(embedded).hexdigest()}
(ROOT/'work'/'expression-package-validation.json').write_text(json.dumps(report, indent=2)+'\n')
print('Verified all 9 embedded expression PNGs against the source files.', flush=True)
