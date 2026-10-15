"""Verify downloaded source assets and prepare the local frame-pack build."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''):
            value.update(block)
    return value.hexdigest()


def prepare(check_only=False):
    assets = ROOT/'assets'
    manifest = json.loads((assets/'manifest.json').read_text(encoding='utf-8'))
    checksums = json.loads((assets/'source-checksums.json').read_text(encoding='utf-8'))['files']
    names = [spec['file'] for spec in manifest['animations'].values()]
    for name in names:
        if Path(name).name != name:
            raise ValueError('Asset filenames must stay inside assets: '+name)
        path = assets/name
        if not path.is_file():
            raise FileNotFoundError(
                f'Missing assets/{name}. Download CitlaliDesktopPet-source-assets.zip '
                'from GitHub Releases and extract it into the project root. See docs/PUBLISHING.md.')
        expected = checksums[name]
        if path.stat().st_size != expected['bytes'] or digest(path) != expected['sha256']:
            raise ValueError('Source asset does not match its checksum: '+name)
    for motion in ('dragging', 'stomping'):
        folder = assets/motion
        if (folder/'source.json').is_file():
            metadata = json.loads((folder/'source.json').read_text(encoding='utf-8'))
            for name,expected in metadata['files'].items():
                path = folder/name
                if path.stat().st_size != expected['bytes'] or digest(path) != expected['sha256']:
                    raise ValueError(motion+' animation does not match its checksum: '+name)
    if not check_only:
        stage = ROOT/'work'/'repaired-assets'
        stage.mkdir(parents=True, exist_ok=True)
        for name in names+['manifest.json']:
            source, target = assets/name, stage/name
            if not target.exists() or digest(source) != digest(target):
                shutil.copy2(source, target)
    print('Verified all 3 source animations'+(' (check only)' if check_only else '; build assets prepared'), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    try:
        prepare(args.check_only)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, str(error)+'\n')
