"""Verify either legacy separate motion packs or the combined compact pack."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent


def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):
            value.update(block)
    return value.hexdigest()


def verify_motion(archive,names,motion):
    folder=ROOT/'assets'/motion
    metadata=json.loads((folder/'source.json').read_text(encoding='utf-8'))
    assert json.loads(archive.extract(names[f'assets/{motion}/source.json'])) == metadata
    if f'assets/{motion}/pet-frames.bin' in names:
        for name,expected in metadata['files'].items():
            payload=archive.extract(names[f'assets/{motion}/{name}'])
            assert len(payload) == expected['bytes'] and hashlib.sha256(payload).hexdigest() == expected['sha256']
    else:
        stage=ROOT/'work/repaired-assets'
        index=json.loads(archive.extract(names['assets/pet-frames.json']))
        assert index == json.loads((stage/'pet-frames.json').read_text(encoding='utf-8'))
        assert index['version'] == 2 and index['codec'] == 'webp-lossless-native-delta'
        payload=archive.extract(names['assets/'+index['data']])
        assert len(payload) == index['data_bytes']
        assert hashlib.sha256(payload).hexdigest() == digest(stage/index['data'])
        assert len(index['animations'][motion]['frames']) == metadata['output_frames']
        for name,expected in metadata['files'].items():
            assert index['source_files'][f'assets/{motion}/{name}'] == expected
    return metadata
