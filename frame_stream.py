"""Bounded, asynchronous playback of independently compressed lossless frames."""
from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading
import zlib

from PIL import Image, ImageChops


def pack_frame(rgba):
    bbox = rgba.getbbox()
    if bbox is None:
        raise ValueError('Empty animation frame')
    tile = rgba.crop(bbox)
    r, g, b, a = tile.split()
    pixels = Image.merge('RGBA', (ImageChops.multiply(r, a), ImageChops.multiply(g, a),
                                  ImageChops.multiply(b, a), a)).tobytes('raw', 'BGRA')
    return {'pixels': pixels, 'offset': bbox[:2], 'size': tile.size}


class FrameArchive:
    def __init__(self, path):
        path = Path(path)
        data = json.loads(path.read_text(encoding='utf-8'))
        if data['version'] != 1:
            raise ValueError('Unsupported frame archive')
        self.path = path.parent/data['data']
        if self.path.stat().st_size != data['data_bytes']:
            raise ValueError('Incomplete frame archive')
        self.canvas = tuple(data['canvas'])
        self.display_canvas = tuple(data['display_canvas'])
        self.animations = {}
        self.sources = {}
        for name, spec in data['animations'].items():
            endpoints = []
            duration = 0.0
            for frame in spec['frames']:
                duration += max(1, frame['ms'])/1000
                endpoints.append(duration)
            self.animations[name] = {'frames': spec['frames'], 'endpoints': endpoints, 'duration': duration}
            self.sources[name] = self.path

    def include(self, path):
        other = FrameArchive(path)
        if (other.canvas,other.display_canvas) != (self.canvas,self.display_canvas):
            raise ValueError('Animation canvas sizes must match')
        if self.animations.keys() & other.animations.keys():
            raise ValueError('Duplicate animation in optional archive')
        self.animations.update(other.animations)
        self.sources.update(other.sources)

    def read(self, name, number, size):
        display = size == self.display_canvas
        record = self.animations[name]['frames'][number]['display' if display else 'native']
        offset, length, x, y, right, bottom = record
        with self.sources[name].open('rb') as source:
            source.seek(offset)
            data = source.read(length)
        pixels = zlib.decompress(data)
        width, height = right-x, bottom-y
        if len(pixels) != width*height*4:
            raise ValueError('Invalid frame record')
        if display:
            return {'pixels': pixels, 'offset': (x, y), 'size': (width, height)}
        tile = Image.frombytes('RGBA', (width, height), pixels)
        rgba = Image.new('RGBA', self.canvas)
        rgba.paste(tile, (x, y))
        # Fixed-canvas Lanczos sampling preserves native detail and alignment.
        return pack_frame(rgba.resize(size, Image.Resampling.LANCZOS))


class FrameStream:
    """Eight frames of lookahead; at most 12 frames / 24 MiB cached."""
    def __init__(self, archive):
        self.archive = archive
        self.cache = OrderedDict()
        self.cache_bytes = 0
        self.peak_cache_bytes = 0
        self.peak_cache_frames = 0
        self.condition = threading.Condition()
        self.plan = None
        self.stopped = False
        self.error = None
        self.worker = threading.Thread(target=self._work, name='PetFrameReader', daemon=True)
        self.worker.start()

    def get(self, name, number, size):
        if not 0 <= number < len(self.archive.animations[name]['frames']):
            raise IndexError(f'Animation frame out of range: {name} {number}')
        key = (name, number, size)
        with self.condition:
            self.plan = key
            self.condition.notify()
            while key not in self.cache:
                if self.error:
                    raise RuntimeError('Animation reader failed') from self.error
                if self.stopped:
                    raise RuntimeError('Animation reader closed')
                self.condition.wait()
            self.cache.move_to_end(key)
            return self.cache[key]

    def clear(self):
        with self.condition:
            self.plan = None
            self.cache.clear()
            self.cache_bytes = 0
            self.condition.notify_all()

    def close(self):
        with self.condition:
            self.stopped = True
            self.condition.notify_all()
        self.worker.join()

    def _work(self):
        pending = {}
        pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix='PetFrameDecode')
        try:
            while True:
                with self.condition:
                    if self.stopped:
                        return
                    plan = self.plan
                    for key, future in list(pending.items()):
                        if not future.done():
                            continue
                        frame = future.result()
                        del pending[key]
                        if plan is None or (key[0], key[2]) != (plan[0], plan[2]):
                            continue
                        self.cache[key] = frame
                        self.cache_bytes += len(frame['pixels'])
                        while len(self.cache) > 12 or self.cache_bytes > 24*1024*1024:
                            _, old = self.cache.popitem(last=False)
                            self.cache_bytes -= len(old['pixels'])
                        self.peak_cache_bytes = max(self.peak_cache_bytes, self.cache_bytes)
                        self.peak_cache_frames = max(self.peak_cache_frames, len(self.cache))
                        self.condition.notify_all()
                if plan is None:
                    with self.condition:
                        self.condition.wait_for(lambda: self.stopped or self.plan is not None)
                    continue
                name, start, size = plan
                count = len(self.archive.animations[name]['frames'])
                desired = [(name, (start+ahead) % count, size) for ahead in range(9)]
                with self.condition:
                    missing = [key for key in desired if key not in self.cache and key not in pending]
                if missing and len(pending) < 3:
                    key = missing[0]
                    pending[key] = pool.submit(self.archive.read, *key)
                elif pending:
                    next(iter(pending.values())).result()
                else:
                    with self.condition:
                        # clear() may invalidate the cache while a resize keeps
                        # exactly the same plan; a missing current frame must wake us.
                        self.condition.wait_for(lambda: self.stopped or self.plan != plan or plan not in self.cache)
        except Exception as error:
            with self.condition:
                self.error = error
                self.condition.notify_all()
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
