"""Reconcile local voice indexes and prepare PCM playback; never download audio."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import wave


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(root):
    local = root/'local-media'/'citlali-voices-zh-cn'
    if not local.is_dir():
        folder = root/'assets'/'voices'
        return folder if (folder/'catalog.json').is_file() else None
    manifest_path = local/'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    backup = local/'manifest.before-menu.json'
    if not backup.exists():
        shutil.copy2(manifest_path, backup)
    selected = []
    excluded = {r['id']:r for r in manifest.get('excluded_records', [])}
    candidates = {r['id']:r for r in [*excluded.values(), *manifest['records']]}
    for record in candidates.values():
        relative = record.get('file')
        path = (local/relative).resolve() if relative else None
        if path and not path.is_relative_to(local.resolve()):
            raise ValueError('Voice path escapes the local folder')
        if path and path.is_file():
            selected.append(dict(record, status='downloaded', bytes=path.stat().st_size, sha256=digest(path)))
            excluded.pop(record['id'], None)
        else:
            excluded[record['id']] = dict(record, status='removed_by_user' if relative else 'source_missing')
    selected.sort(key=lambda r:r['id'])
    output = local/'_playback'
    output.mkdir(exist_ok=True)
    catalog_path = output/'catalog.json'
    previous = json.loads(catalog_path.read_text(encoding='utf-8'))['records'] if catalog_path.exists() else []
    old = {r['id']:r for r in previous}
    ffmpeg = shutil.which('ffmpeg')

    def convert(record):
        source = local/record['file']
        target = output/f"{record['id']:03d}.wav"
        cached = old.get(record['id'], {})
        if not target.is_file() or cached.get('source_sha256') != record['sha256'] or cached.get('sha256') != digest(target):
            if not ffmpeg:
                raise FileNotFoundError('Install ffmpeg to prepare the selected Ogg voices')
            temporary = target.with_suffix('.part.wav')
            subprocess.run([ffmpeg,'-nostdin','-v','error','-y','-i',str(source),'-map','0:a:0',
                '-map_metadata','-1','-c:a','pcm_s16le','-fflags','+bitexact','-flags:a','+bitexact',str(temporary)],
                check=True,capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
            temporary.replace(target)
        with wave.open(str(target), 'rb') as stream:
            assert stream.getsampwidth() == 2 and stream.getcomptype() == 'NONE'
            duration = stream.getnframes()/stream.getframerate()
            channels, rate = stream.getnchannels(), stream.getframerate()
        return {'id':record['id'],'title':record['title'],'category':record['category'],
                'file':target.name,'source_file':record['file'],'source_sha256':record['sha256'],
                'sha256':digest(target),'bytes':target.stat().st_size,'duration_seconds':duration,
                'sample_rate':rate,'channels':channels}

    with ThreadPoolExecutor(max_workers=3) as pool:
        playback = list(pool.map(convert, selected))
    catalog_path.write_text(json.dumps({'language':'zh-CN','records':playback},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    manifest['records'] = selected
    manifest['excluded_records'] = sorted(excluded.values(),key=lambda r:r['id'])
    manifest['selection_updated_at'] = datetime.now(timezone.utc).isoformat()
    manifest['summary'].update(downloaded=len(selected), active=len(selected),
        removed_by_user=sum(r['status']=='removed_by_user' for r in excluded.values()),
        source_missing=sum(r['status']=='source_missing' for r in excluded.values()),
        total_bytes=sum(r['bytes'] for r in selected),
        total_duration_seconds=sum(r['duration_seconds'] for r in selected))
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with (local/'语音索引.csv').open('w',encoding='utf-8-sig',newline='') as output_csv:
        writer = csv.writer(output_csv)
        writer.writerow(['编号','分类','语音名称','文件','时长（秒）','状态','中文文本','原始链接','SHA256'])
        for record in selected:
            writer.writerow([record['id'],record['category'],record['title'],record['file'],
                record['duration_seconds'],'downloaded',record['text_zh'],record['source_url'],record['sha256']])
    (local/'SHA256SUMS.txt').write_text(''.join(f"{r['sha256']}  {r['file']}\n" for r in selected),encoding='utf-8')
    (local/'README.md').write_text('# 茜特菈莉中文语音（当前保留）\n\n'
        f'当前保留 {len(selected)} 条语音，索引仅列出仍存在的文件。已删除的选择保存在 manifest.json 的 excluded_records 中，不会被本脚本重新下载。\n\n'
        '角色语音目录保存原始 OGG，_playback 保存同采样率的 PCM WAV，用于 Windows 原生播放。整个目录由 Git 忽略。\n\n'
        '重新扫描并准备播放文件：python work/prepare_voices.py\n',encoding='utf-8')
    print(f'Prepared {len(selected)} selected voices; excluded {len(excluded)} unavailable/removed entries.',flush=True)
    return local/'_playback'


if __name__ == '__main__':
    prepare(Path(__file__).resolve().parent.parent)
