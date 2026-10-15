"""Extract one complete stomp from the supplied GIF and interpolate to 60 FPS.

The imagegen output supplies alpha guidance only. Animated RGB always comes
from the user's original GIF, and no absent character parts are synthesized.
"""
from bisect import bisect_right
import hashlib
import json
from pathlib import Path
import sys
import zlib

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT/'work'/'sources'/'drag-deps'))
import cv2
import numpy as np
from PIL import Image, ImageDraw

LOCAL = ROOT/'local-media'/'shake-interaction'
OUTPUT = ROOT/'assets'/'stomping'
SOURCE_FRAMES = range(11, 19)  # One stomp, with both hands inside the image.
cv2.setNumThreads(3)


def encode(stream, image, premultiplied=False):
    bounds = image.getbbox()
    tile = np.asarray(image.crop(bounds)).copy()
    if premultiplied:
        tile[:, :, :3] = tile[:, :, :3].astype('uint16')*tile[:, :, 3:4]//255
        tile = tile[:, :, [2, 1, 0, 3]]
    packed = zlib.compress(tile.tobytes(), 3)
    record = [stream.tell(), len(packed), *bounds]
    stream.write(packed)
    return record


def matte():
    guides = {}
    for number, prefix in ((10, 'mask'), (18, 'mask-end')):
        alpha = np.asarray(Image.open(LOCAL/(prefix+'-reference.png')).getchannel('A').resize((390, 596)))
        rgb = np.asarray(Image.open(LOCAL/(prefix+'-source.png')).convert('RGB'))
        guides[number] = (cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), alpha)
    tracker = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    frames = []
    yy, xx = np.mgrid[:596, :390].astype('float32')
    with Image.open(LOCAL/'source.gif') as source:
        for number in range(10, 19):
            source.seek(number)
            rgb = np.asarray(source.convert('RGB'))
            gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
            reference_gray, reference_alpha = guides[10 if number <= 12 else 18]
            flow = tracker.calc(gray, reference_gray, None)
            prior = cv2.remap(reference_alpha, xx+flow[:, :, 0], yy+flow[:, :, 1], cv2.INTER_LINEAR)
            inside = (prior > 110).astype('uint8')
            core = cv2.erode(inside, np.ones((7, 7), 'uint8')) > 0
            fringe = cv2.dilate(inside, np.ones((15, 15), 'uint8')) > 0
            labels = np.zeros(gray.shape, 'uint8')
            labels[fringe] = cv2.GC_PR_BGD
            labels[inside > 0] = cv2.GC_PR_FGD
            red, green, blue = rgb.astype('int16').transpose(2, 0, 1)
            scenery = ((green > red+3) & (blue > red+12)) | ((green > red+12) & (green > blue+5))
            hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
            saturated_scenery = (hsv[:, :, 0] >= 60) & (hsv[:, :, 0] < 119) & (hsv[:, :, 1] > 50)
            labels[core] = cv2.GC_FGD
            labels[scenery & ~inside.astype(bool)] = cv2.GC_BGD
            labels[saturated_scenery] = cv2.GC_BGD
            # Retain every visible pixel when the source pose approaches its
            # image border; a fixed strip would shave the sleep mask/soles.
            labels[0, prior[0] < 64] = cv2.GC_BGD
            labels[-1, prior[-1] < 64] = cv2.GC_BGD
            cv2.grabCut(rgb, labels, None, np.zeros((1, 65), 'float64'),
                        np.zeros((1, 65), 'float64'), 5, cv2.GC_INIT_WITH_MASK)
            mask = np.isin(labels, (cv2.GC_FGD, cv2.GC_PR_FGD)).astype('uint8')
            count, components, stats, _ = cv2.connectedComponentsWithStats(mask)
            primary = 1+int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
            keep = [primary]
            nearby = cv2.dilate((components == primary).astype('uint8'), np.ones((9, 9), 'uint8')) > 0
            purple = (red > green+8) & (blue > green+12)
            for part in range(1, count):
                selected = components == part
                if part != primary and stats[part, cv2.CC_STAT_AREA] >= 4 and np.any(nearby & selected) and np.mean(purple[selected]) > .4:
                    keep.append(part)
            mask = np.isin(components, keep).astype('uint8')
            alpha = cv2.GaussianBlur(mask.astype('float32'), (0, 0), .55)
            rgba = np.dstack((rgb, np.uint8(np.clip(alpha*255+.5, 0, 255))))
            rgba[rgba[:, :, 3] == 0, :3] = 0
            Image.fromarray(rgba).save(LOCAL/f'matte-{number:03}.png')
            if number in SOURCE_FRAMES:
                frames.append(rgba)
            print('Matted source frame', number, flush=True)
    return frames


def build():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    frames = matte()
    # Let the raised foot and the final pout read clearly before fading back.
    durations = [.09]*len(frames)
    durations[-1] += .28
    endpoints = np.cumsum(durations)
    total = round(float(endpoints[-1])*60)
    interpolator = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    yy, xx = np.mgrid[:596, :390].astype('float32')
    record = {'version': 1, 'canvas': [840, 720], 'display_canvas': [560, 480],
              'data': 'pet-frames.bin', 'animations': {'stomping': {'frames': []}}}
    previous_pair = None
    previews = []
    changes = []
    last = None
    with (OUTPUT/'pet-frames.bin').open('wb') as stream:
        for number in range(total):
            timestamp = number/60
            index = min(bisect_right(endpoints, timestamp), len(frames)-1)
            start = float(endpoints[index-1]) if index else 0
            fraction = (timestamp-start)/durations[index] if index < len(frames)-1 else 0
            if index != previous_pair:
                a, b = frames[index], frames[min(index+1, len(frames)-1)]
                ga, gb = (cv2.cvtColor(frame[:, :, :3], cv2.COLOR_RGB2GRAY) for frame in (a, b))
                forward = interpolator.calc(ga, gb, None)
                backward = interpolator.calc(gb, ga, None)
                pa, pb = a.astype('float32'), b.astype('float32')
                pa[:, :, :3] *= pa[:, :, 3:4]/255
                pb[:, :, :3] *= pb[:, :, 3:4]/255
                previous_pair = index
            wa = cv2.remap(pa, xx-forward[:, :, 0]*fraction, yy-forward[:, :, 1]*fraction, cv2.INTER_LINEAR)
            wb = cv2.remap(pb, xx-backward[:, :, 0]*(1-fraction), yy-backward[:, :, 1]*(1-fraction), cv2.INTER_LINEAR)
            rgba = wa*(1-fraction)+wb*fraction
            rgba[:, :, :3] = np.divide(rgba[:, :, :3]*255, rgba[:, :, 3:4],
                                      out=np.zeros_like(rgba[:, :, :3]), where=rgba[:, :, 3:4] > 0)
            tile = Image.fromarray(np.uint8(np.clip(rgba, 0, 255)))
            canvas = Image.new('RGBA', (840, 720))
            canvas.paste(tile, (239, 104))
            display = canvas.resize((560, 480), Image.Resampling.LANCZOS)
            native, small = encode(stream, canvas), encode(stream, display, True)
            ms = round((number+1)*1000/60)-round(number*1000/60)
            record['animations']['stomping']['frames'].append({'ms': ms, 'native': native, 'display': small})
            premultiplied = np.asarray(display).astype('float32')
            premultiplied[:, :, :3] *= premultiplied[:, :, 3:4]/255
            if last is not None:
                changes.append(float(np.abs(premultiplied-last).mean()))
            last = premultiplied
            if number in (0, 6, 12, 20, 30, 45):
                previews.append(display)
            if number == 0:
                display.save(ROOT/'work'/'stomping-cutout.png')
    record['data_bytes'] = (OUTPUT/'pet-frames.bin').stat().st_size
    (OUTPUT/'pet-frames.json').write_text(json.dumps(record, separators=(',', ':'))+'\n', encoding='utf-8')
    metadata = {'version': 1, 'source_file': '8d8b557ec2dc9b49294c660c96fb38c2.gif',
                'source_sha256': hashlib.sha256((LOCAL/'source.gif').read_bytes()).hexdigest(),
                'source_total_frames': 85, 'source_selected_frames': list(SOURCE_FRAMES),
                'output_frames': total, 'duration_ms': sum(f['ms'] for f in record['animations']['stomping']['frames']),
                'fps': 60, 'canvas': record['canvas'], 'display_canvas': record['display_canvas'],
                'layout_native_offset': [239, 104], 'one_shot': True,
                'original_gif_colours': True, 'mask_reference': {'tool': 'image_gen__imagegen', 'mode': 'built-in',
                'prompt': (LOCAL/'mask-prompt.txt').read_text(encoding='utf-8'),
                'use': 'Alpha guidance only; animated RGB is sampled from the original GIF.'},
                'end_mask_reference': {'tool': 'image_gen__imagegen', 'mode': 'built-in',
                'prompt': (LOCAL/'mask-end-prompt.txt').read_text(encoding='utf-8')},
                'files': {name: {'bytes': (OUTPUT/name).stat().st_size,
                                'sha256': hashlib.sha256((OUTPUT/name).read_bytes()).hexdigest()}
                          for name in ('pet-frames.bin', 'pet-frames.json')}}
    (OUTPUT/'source.json').write_text(json.dumps(metadata, indent=2)+'\n', encoding='utf-8')
    contact = Image.new('RGB', (3*280, 2*240), '#eadfe7')
    for i, frame in enumerate(previews):
        tile = Image.new('RGBA', frame.size, '#eadfe7')
        tile.alpha_composite(frame)
        contact.paste(tile.convert('RGB').resize((280, 240)), ((i % 3)*280, (i//3)*240))
    contact.save(ROOT/'work'/'stomping-contact.jpg')
    print(json.dumps({'frames': total, 'duration_ms': metadata['duration_ms'],
                      'pack_bytes': record['data_bytes'], 'max_frame_difference': max(changes)}), flush=True)


if __name__ == '__main__':
    build()
