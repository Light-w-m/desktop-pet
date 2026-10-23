"""Validate every embedded voice against the selection used for this build."""
import hashlib
import io
import json
from pathlib import Path
import sys
import wave

from PyInstaller.archive.readers import CArchiveReader

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'src'))
from citlali_pet.audio.voice_library import runtime_folder

folder = runtime_folder(ROOT)
catalog = json.loads((folder/'catalog.json').read_text(encoding='utf-8'))
archive = CArchiveReader(str(ROOT/'work'/'dist'/'CitlaliDesktopPet.exe'))
names = {name.replace('\\','/'):name for name in archive.toc}
embedded = archive.extract(names['assets/voices/catalog.json'])
assert json.loads(embedded) == catalog
for record in catalog['records']:
    payload = archive.extract(names['assets/voices/'+record['file']])
    assert len(payload) == record['bytes']
    assert hashlib.sha256(payload).hexdigest() == record['sha256']
    with wave.open(io.BytesIO(payload),'rb') as source:
        assert source.getsampwidth() == 2 and source.getcomptype() == 'NONE'
        assert source.getframerate() == record['sample_rate']
        assert source.getnchannels() == record['channels']
report = {'embedded_voices':len(catalog['records']), 'selection_matches':True,
          'all_pcm_wav_headers_and_sha256_verified':True}
(ROOT/'work'/'voice-package-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2),flush=True)
