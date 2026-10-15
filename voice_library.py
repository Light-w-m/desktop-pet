"""Discover selected local voices without reviving recordings the user removed."""
import json
from pathlib import Path

LOCAL_VOICES = Path('local-media/citlali-voices-zh-cn')


def contained(folder, name):
    path = (folder/name).resolve()
    if not path.is_relative_to(folder.resolve()):
        raise ValueError('Voice path escapes its folder')
    return path


def runtime_folder(root):
    local = root/LOCAL_VOICES
    return local/'_playback' if local.is_dir() else root/'assets'/'voices'


class VoiceLibrary:
    def __init__(self, app_dir, resources):
        local = app_dir/LOCAL_VOICES
        self.originals = local if local.is_dir() else None
        external = app_dir/'assets'/'voices'
        self.folder = local/'_playback' if self.originals else (
            external if (external/'catalog.json').is_file() else resources/'assets'/'voices')
        self.records = []
        self.refresh()

    def refresh(self):
        catalog = self.folder/'catalog.json'
        records = json.loads(catalog.read_text(encoding='utf-8')).get('records', []) if catalog.is_file() else []
        selected = []
        for record in records:
            if self.originals and not contained(self.originals, record['source_file']).is_file():
                continue
            path = contained(self.folder, record['file'])
            if path.is_file():
                selected.append(dict(record, path=path))
        self.records = selected
        return selected

    def get(self, identifier):
        record = next(r for r in self.records if r['id'] == identifier)
        if not record['path'].is_file() or (
                self.originals and not contained(self.originals, record['source_file']).is_file()):
            raise FileNotFoundError('Selected voice was removed')
        return record
