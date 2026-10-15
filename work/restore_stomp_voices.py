"""Explicitly restore only the five Chinese recordings used by the stomp reaction."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

from prepare_voices import prepare

ROOT = Path(__file__).resolve().parent.parent
PAGE = 'https://wiki.biligame.com/ys/%E8%8C%9C%E7%89%B9%E8%8F%88%E8%8E%89%E8%AF%AD%E9%9F%B3'
# Original index IDs and checksums, retained when the user removed these files.
RECORDINGS = {
    51: '1f83210f5c8fd340905357cf98cc4d374c88ae58a0a64a1efae583ffe971688b',
    52: '549eb240ba1c8ed61bc31af44d7ec0e88c4e052697daefbe1a5d45af22444cda',
    53: '4dcc91ea324cdee0a737a6d4bb63bc266cb0132c09e5c6a1a563c293b5c5f60f',
    65: '853e79ecc84e20a89f794f2bad1c05a04fa46aa42965b28fbd0988b6684ce13a',
    66: '6342880dd4b49f3aad69475b902462b881fcf986152d5c276e16ac3ad88f14cf',
}


def restore(root=ROOT):
    folder = root/'local-media'/'citlali-voices-zh-cn'
    manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    records = {r['id']: r for r in manifest['records']+manifest.get('excluded_records', [])}

    def download(identifier):
        record = records[identifier]
        assert record['language'] == 'zh-CN'
        target = (folder/record['file']).resolve()
        if not target.is_relative_to(folder.resolve()):
            raise ValueError('Voice path escapes its folder')
        expected = RECORDINGS[identifier]
        if target.is_file():
            assert hashlib.sha256(target.read_bytes()).hexdigest() == expected
            return
        assert record['source_url'].startswith('https://patchwiki.biligame.com/')
        for attempt in range(3):
            try:
                request = Request(record['source_url'], headers={
                    'User-Agent': 'Mozilla/5.0', 'Referer': PAGE, 'Accept-Encoding': 'identity'})
                with urlopen(request, timeout=45) as response:
                    payload = response.read(2*1024*1024)
                assert payload.startswith(b'OggS'), 'Expected the original Ogg recording'
                assert hashlib.sha256(payload).hexdigest() == expected, 'Original recording changed'
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
                print(f"Restored {identifier}: {record['title']}", flush=True)
                return
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(attempt+1)

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(download, RECORDINGS))
    prepare(root)


if __name__ == '__main__':
    restore()
