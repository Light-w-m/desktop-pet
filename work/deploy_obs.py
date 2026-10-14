"""Deploy the verified OBS build and verify every copied file's hash."""
from pathlib import Path
import json
import hashlib
import shutil

root=Path(__file__).resolve().parent.parent
stage=root/'work'/'repaired-assets'
manifest=json.loads((stage/'manifest.json').read_text(encoding='utf-8'))
assert manifest['version']>=4
validation=json.loads((root/'work'/'exe-playback-validation.json').read_text(encoding='utf-8'))
assert validation.get('verified_switches'),'Packaged transitions have not been checked'
for name in manifest['animations']:assert validation[name]['fps']>57

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

pairs=[(stage/'manifest.json',root/'assets'/'manifest.json')]
pairs += [(stage/spec['file'],root/'assets'/spec['file']) for spec in manifest['animations'].values()]
pairs += [(root/'work'/'dist'/'CitlaliDesktopPet.exe',root/'CitlaliDesktopPet.exe'),(stage/manifest['animations']['standing']['file'],root/'standing-preview.webp')]
for source,target in pairs:
    shutil.copy2(source,target)
    assert digest(source)==digest(target),'Copy differs: '+str(target)
    print('Verified',target.name,flush=True)
