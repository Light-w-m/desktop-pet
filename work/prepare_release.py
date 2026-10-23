"""Prepare local GitHub Release attachments; never upload or publish them."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent.parent


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''):
            value.update(block)
    return value.hexdigest()


def prepare(executable):
    assets = ROOT/'assets'
    manifest = json.loads((assets/'manifest.json').read_text(encoding='utf-8'))
    files = {}
    for spec in manifest['animations'].values():
        name = spec['file']
        if Path(name).name != name:
            raise ValueError('Asset filenames must stay inside assets: '+name)
        path = assets/name
        files[name] = {'bytes': path.stat().st_size, 'sha256': digest(path)}
    if not executable.is_file():
        raise FileNotFoundError(executable)
    output = ROOT/'release'
    output.mkdir(exist_ok=True)
    (assets/'source-checksums.json').write_text(json.dumps({'version':1,'files':files},indent=2)+'\n',encoding='utf-8')
    destination = output/'CitlaliDesktopPet.exe'
    shutil.copy2(executable, destination)
    executable_hash = digest(executable)
    assert digest(destination) == executable_hash, 'Executable copy differs'
    archive = output/'CitlaliDesktopPet-source-assets.zip'
    names = list(files)+['manifest.json','source-checksums.json']
    voice_root = ROOT/'local-media'/'citlali-voices-zh-cn'
    voices = voice_root/'_playback' if voice_root.is_dir() else assets/'voices'
    voice_catalog = json.loads((voices/'catalog.json').read_text(encoding='utf-8')) if (voices/'catalog.json').is_file() else None
    extra = ({'assets/voices/'+name:voices/name for name in
              ['catalog.json']+[r['file'] for r in voice_catalog['records']]} if voice_catalog else {})
    motion_metadata = {}
    for motion in ('dragging', 'stomping', 'walking'):
        folder = assets/motion
        if (folder/'source.json').is_file():
            motion_metadata[motion] = json.loads((folder/'source.json').read_text(encoding='utf-8'))
            extra.update({'assets/'+motion+'/'+name:folder/name for name in
                          ('source.json','pet-frames.json','pet-frames.bin')})
    # WebP files are already compressed; store them without another costly pass.
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_STORED) as package:
        for name in names:
            package.write(assets/name, 'assets/'+name)
        for name, path in extra.items():
            if path.suffix in ('.wav','.json'):
                package.write(path,name,compress_type=zipfile.ZIP_DEFLATED,compresslevel=6)
            else:
                package.write(path,name)
    with zipfile.ZipFile(archive) as package:
        assert set(package.namelist()) == {'assets/'+name for name in names} | set(extra)
        for name, expected in files.items():
            value = hashlib.sha256()
            with package.open('assets/'+name) as source:
                for block in iter(lambda: source.read(1024*1024), b''):
                    value.update(block)
            assert value.hexdigest() == expected['sha256'], 'Archive differs: '+name
        assert json.loads(package.read('assets/manifest.json')) == manifest
        if voice_catalog:
            assert json.loads(package.read('assets/voices/catalog.json')) == voice_catalog
            for record in voice_catalog['records']:
                assert hashlib.sha256(package.read('assets/voices/'+record['file'])).hexdigest() == record['sha256']
        for motion, metadata in motion_metadata.items():
            for name,expected in metadata['files'].items():
                assert hashlib.sha256(package.read('assets/'+motion+'/'+name)).hexdigest() == expected['sha256']
    shutil.copy2(ROOT/'docs'/'RELEASE_NOTES.md', output/'RELEASE_NOTES.md')
    (output/'SHA256SUMS.txt').write_text(
        f'{executable_hash}  {destination.name}\n{digest(archive)}  {archive.name}\n',encoding='utf-8')
    for path in (destination, archive):
        assert path.stat().st_size < 2*1024**3, 'Release attachment exceeds 2 GiB'
        print(f'{path.name}: {path.stat().st_size/1024**2:.1f} MiB',flush=True)
    print('Local release files verified. Publish them yourself using docs/PUBLISHING.md.',flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe',type=Path,default=ROOT/'CitlaliDesktopPet.exe')
    args = parser.parse_args()
    prepare(args.exe.resolve())
