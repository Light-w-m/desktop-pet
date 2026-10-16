"""Bounded, asynchronous playback of lossless animation packs."""
from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import json
import io
from pathlib import Path
import threading
import zlib

# Register the required decoder directly; opening the first WebP must not load
# every unrelated Pillow format (and their native libraries) into the pet.
from PIL import Image, ImageChops, WebPImagePlugin


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
        if data['version'] not in (1, 2):
            raise ValueError('Unsupported frame archive')
        if data['version'] == 2 and data.get('codec') != 'webp-lossless-native-delta':
            raise ValueError('Unsupported compact frame codec')
        self.path = path.parent/data['data']
        if self.path.stat().st_size != data['data_bytes']:
            raise ValueError('Incomplete frame archive')
        self.canvas = tuple(data['canvas'])
        self.display_canvas = tuple(data['display_canvas'])
        self.animations = {}
        self.sources = {}
        self.formats = {}
        self.raw_cache = OrderedDict()
        self.raw_cache_bytes = self.peak_raw_cache_bytes = 0
        self.raw_lock = threading.RLock()
        for name, spec in data['animations'].items():
            endpoints = []
            duration = 0.0
            for frame in spec['frames']:
                duration += max(1, frame['ms'])/1000
                endpoints.append(duration)
            self.animations[name] = {'frames': spec['frames'], 'endpoints': endpoints, 'duration': duration}
            self.sources[name] = self.path
            self.formats[name] = data['version']

    def include(self, path):
        other = FrameArchive(path)
        if (other.canvas,other.display_canvas) != (self.canvas,self.display_canvas):
            raise ValueError('Animation canvas sizes must match')
        if self.animations.keys() & other.animations.keys():
            raise ValueError('Duplicate animation in optional archive')
        self.animations.update(other.animations)
        self.sources.update(other.sources)
        self.formats.update(other.formats)

    def _native(self, name, number):
        # A short dependency chain shares its native bytes between neighboring
        # reads. Keep this cache bounded, including when resizing or warming a
        # different animation. Resizing runs outside the decoder lock.
        key = name, number
        with self.raw_lock:
            if key in self.raw_cache:
                self.raw_cache.move_to_end(key)
                return self.raw_cache[key]
            frame = self.animations[name]['frames'][number]
            offset,length,x,y,right,bottom = frame['native']
            with self.sources[name].open('rb') as source:
                source.seek(offset)
                encoded = source.read(length)
            with Image.open(io.BytesIO(encoded)) as source:
                tile = source.convert('RGBA')
            if tile.size != (right-x,bottom-y):
                raise ValueError('Invalid compact frame dimensions')
            base = frame.get('base')
            if base is not None:
                if (not 0 <= base < number or base != number-1 or frame.get('depth',0) not in range(1,8) or
                        frame['depth'] != self.animations[name]['frames'][base].get('depth',0)+1):
                    raise ValueError('Invalid compact frame dependency')
                previous,box = self._native(name,base)
                aligned = Image.new('RGBA',tile.size)
                aligned.paste(Image.frombytes('RGBA',(box[2]-box[0],box[3]-box[1]),previous),
                              (box[0]-x,box[1]-y))
                tile = ImageChops.add_modulo(tile,aligned)
            pixels = tile.tobytes()
            result = pixels,(x,y,right,bottom)
            self.raw_cache[key] = result
            self.raw_cache_bytes += len(pixels)
            while len(self.raw_cache) > 12 or self.raw_cache_bytes > 16*1024*1024:
                _,old = self.raw_cache.popitem(last=False)
                self.raw_cache_bytes -= len(old[0])
            self.peak_raw_cache_bytes = max(self.peak_raw_cache_bytes,self.raw_cache_bytes)
            return result

    def read(self, name, number, size):
        if self.formats[name] == 2:
            pixels,box = self._native(name,number)
            tile = Image.frombytes('RGBA',(box[2]-box[0],box[3]-box[1]),pixels)
            rgba = Image.new('RGBA',self.canvas)
            rgba.paste(tile,box[:2])
            return pack_frame(rgba.resize(size,Image.Resampling.LANCZOS))
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
        self.warm = ()
        self.generation = 0
        self.stopped = False
        self.error = None
        self.worker = threading.Thread(target=self._work, name='PetFrameReader', daemon=True)
        self.worker.start()

    def _key(self, name, number, size):
        if not 0 <= number < len(self.archive.animations[name]['frames']):
            raise IndexError(f'Animation frame out of range: {name} {number}')
        return name, number, size

    def request(self, name, number, size):
        """Select the playback plan without blocking the window thread."""
        key = self._key(name, number, size)
        with self.condition:
            self.plan = key
            self.condition.notify_all()

    def prefetch(self, keys=()):
        """Warm up to three transition frames alongside the current animation."""
        keys = tuple(dict.fromkeys(self._key(*key) for key in keys))
        if len(keys) > 3:
            raise ValueError('At most three transition frames may be warmed')
        with self.condition:
            if keys != self.warm:
                self.warm = keys
                self.condition.notify_all()

    def peek(self, name, number, size):
        """Return a prepared frame, or None; never switch plans or wait for I/O."""
        key = self._key(name, number, size)
        with self.condition:
            if self.error:
                raise RuntimeError('Animation reader failed') from self.error
            frame = self.cache.get(key)
            if frame is not None:
                self.cache.move_to_end(key)
            return frame

    def get(self, name, number, size):
        key = self._key(name, number, size)
        with self.condition:
            self.plan = key
            self.condition.notify_all()
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
            self.warm = ()
            self.generation += 1
            self.cache.clear()
            self.cache_bytes = 0
            self.condition.notify_all()

    def close(self):
        with self.condition:
            self.stopped = True
            self.condition.notify_all()
        self.worker.join()

    def _desired(self):
        if self.plan is None:
            return list(self.warm)
        name, start, size = self.plan
        count = len(self.archive.animations[name]['frames'])
        # The visible frame has first priority, followed by the transition
        # frames. The nine active frames plus three warm frames share the cap.
        return list(dict.fromkeys([self.plan, *self.warm,
                    *((name, (start+ahead) % count, size) for ahead in range(1, 9))]))

    def _wake(self, future):
        with self.condition:
            self.condition.notify_all()

    def _work(self):
        pending = {}
        pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix='PetFrameDecode')
        try:
            while True:
                with self.condition:
                    if self.stopped:
                        return
                    desired = self._desired()
                    for key, (generation, future) in list(pending.items()):
                        if not future.done():
                            continue
                        frame = future.result()
                        del pending[key]
                        if generation != self.generation or key not in desired:
                            continue
                        previous = self.cache.pop(key, None)
                        if previous:
                            self.cache_bytes -= len(previous['pixels'])
                        self.cache[key] = frame
                        self.cache_bytes += len(frame['pixels'])
                        while len(self.cache) > 12 or self.cache_bytes > 24*1024*1024:
                            victim = next((k for k in self.cache if k not in desired), next(iter(self.cache)))
                            old = self.cache.pop(victim)
                            self.cache_bytes -= len(old['pixels'])
                        self.peak_cache_bytes = max(self.peak_cache_bytes, self.cache_bytes)
                        self.peak_cache_frames = max(self.peak_cache_frames, len(self.cache))
                        self.condition.notify_all()
                    missing = [key for key in desired if key not in self.cache and key not in pending]
                    for key in missing[:max(0, 3-len(pending))]:
                        future = pool.submit(self.archive.read, *key)
                        pending[key] = self.generation, future
                        future.add_done_callback(self._wake)
                    # Completion callbacks wake us without waiting on an old
                    # animation's slowest decode after a transition or resize.
                    if not any(future.done() for _, future in pending.values()):
                        self.condition.wait()
        except Exception as error:
            with self.condition:
                self.error = error
                self.condition.notify_all()
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
