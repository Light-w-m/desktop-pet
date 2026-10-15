"""Matte the supplied GIF, motion-interpolate its loop and build a small frame pack.

Build-only: OpenCV and NumPy are needed here, never in the desktop executable.
The generated cutout is an alpha reference; every animation colour comes from the GIF.
"""
from bisect import bisect_right
import hashlib
import json
from pathlib import Path
import sys
import zlib

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'work'/'sources'/'drag-deps'))
import cv2
import numpy as np
from PIL import Image

LOCAL = ROOT/'local-media'/'drag-interaction'
OUTPUT = ROOT/'assets'/'dragging'
OUTPUT.mkdir(parents=True,exist_ok=True)
cv2.setNumThreads(3)


def encode(stream, image, premultiplied=False):
    bounds = image.getbbox()
    tile = np.asarray(image.crop(bounds)).copy()
    if premultiplied:
        tile[:,:,:3] = (tile[:,:,:3].astype('uint16')*tile[:,:,3:4]//255).astype('uint8')
        tile = tile[:,:,[2,1,0,3]]
    packed = zlib.compress(tile.tobytes(),3)
    record = [stream.tell(),len(packed),*bounds]
    stream.write(packed)
    return record


def matte_frames():
    reference = np.asarray(Image.open(LOCAL/'mask-reference.png').getchannel('A').resize((720,720))) > 96
    previous = None
    prior = reference.astype('uint8')*255
    frames, durations = [],[]
    with Image.open(LOCAL/'source.gif') as source:
        for number in range(source.n_frames):
            source.seek(number)
            rgb = np.asarray(source.convert('RGB'))
            gray = cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
            if previous is not None:
                flow = cv2.calcOpticalFlowFarneback(cv2.resize(gray,(360,360)),
                    cv2.resize(previous,(360,360)),None,.5,3,19,3,5,1.2,0)
                flow = cv2.resize(flow,(720,720))*2
                yy,xx = np.mgrid[:720,:720].astype('float32')
                prior = cv2.remap(prior,xx+flow[:,:,0],yy+flow[:,:,1],cv2.INTER_LINEAR)
            inside = (prior > 128).astype('uint8')
            core = cv2.erode(inside,np.ones((9,9),'uint8')) > 0
            fringe = cv2.dilate(inside,np.ones((19,19),'uint8')) > 0
            labels = np.zeros((720,720),'uint8')
            labels[fringe] = cv2.GC_PR_BGD
            labels[inside > 0] = cv2.GC_PR_FGD
            values = rgb.astype('int16')
            red,green,blue = (values[:,:,i] for i in range(3))
            room = ((values.max(axis=2) < 90) & (blue <= red+3)) | (
                (values.max(axis=2) < 150) & (red > blue+10) & (green > blue+8))
            labels[core & ~room] = cv2.GC_FGD
            labels[room] = cv2.GC_BGD
            labels[:8] = cv2.GC_BGD
            labels[:,-10:] = cv2.GC_BGD
            cv2.grabCut(rgb,labels,None,np.zeros((1,65),'float64'),np.zeros((1,65),'float64'),
                        3 if number == 0 else 2,cv2.GC_INIT_WITH_MASK)
            mask = np.isin(labels,(cv2.GC_FGD,cv2.GC_PR_FGD)).astype('uint8')
            count,components,stats,_ = cv2.connectedComponentsWithStats(mask)
            largest = 1+int(np.argmax(stats[1:,cv2.CC_STAT_AREA]))
            mask = (components == largest).astype('uint8')
            alpha = cv2.GaussianBlur(mask.astype('float32'),(0,0),.65)
            prior = mask*255
            previous = gray
            # The supplied close-up ends at the image border. Soften only those
            # existing cut edges; never invent the missing body or pillow.
            alpha[-24:] *= np.linspace(1,0,24,dtype='float32')[:,None]
            alpha[:,:5] *= np.linspace(0,1,5,dtype='float32')[None,:]
            rgba = np.dstack((rgb,np.uint8(np.clip(alpha*255+.5,0,255))))
            rgba[rgba[:,:,3] == 0,:3] = 0
            premultiplied = rgba.astype('float32')
            premultiplied[:,:,:3] *= premultiplied[:,:,3:4]/255
            reduced = cv2.resize(premultiplied,(510,510),interpolation=cv2.INTER_AREA)
            reduced[:,:,:3] = np.divide(reduced[:,:,:3]*255,reduced[:,:,3:4],
                out=np.zeros_like(reduced[:,:,:3]),where=reduced[:,:,3:4]>0)
            frames.append(np.uint8(np.clip(reduced+.5,0,255)))
            durations.append(source.info.get('duration',40))
            if number % 15 == 0:
                Image.fromarray(rgba).save(LOCAL/f'matte-{number:03}.png')
                print('Matted source frame',number,flush=True)
    return frames,durations


def build():
    frames,durations = matte_frames()
    # Allocate a short bridge to close the recording, instead of snapping the
    # last 24-fps frame back to the first.
    durations[-1] = max(durations[-1],180)
    endpoints = np.cumsum(durations)/1000
    total = round(float(endpoints[-1])*60)
    record = {'version':1,'canvas':[840,720],'display_canvas':[560,480],
              'data':'pet-frames.bin','animations':{'dragging':{'frames':[]}}}
    interpolator = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    yy,xx = np.mgrid[:510,:510].astype('float32')
    previous_pair = None
    preview = []
    changes = []
    first = last = None
    with (OUTPUT/'pet-frames.bin').open('wb') as stream:
        for number in range(total):
            timestamp = number/60
            index = min(bisect_right(endpoints,timestamp),len(frames)-1)
            start = float(endpoints[index-1]) if index else 0
            fraction = (timestamp-start)/(durations[index]/1000)
            if index == len(frames)-1:
                fraction = fraction*fraction*(3-2*fraction)
            if index != previous_pair:
                a,b = frames[index],frames[(index+1)%len(frames)]
                ga,gb = (cv2.cvtColor(frame[:,:,:3],cv2.COLOR_RGB2GRAY) for frame in (a,b))
                forward = interpolator.calc(ga,gb,None)
                backward = interpolator.calc(gb,ga,None)
                pa,pb = a.astype('float32'),b.astype('float32')
                pa[:,:,:3] *= pa[:,:,3:4]/255
                pb[:,:,:3] *= pb[:,:,3:4]/255
                previous_pair = index
            wa = cv2.remap(pa,xx-forward[:,:,0]*fraction,yy-forward[:,:,1]*fraction,cv2.INTER_LINEAR)
            wb = cv2.remap(pb,xx-backward[:,:,0]*(1-fraction),yy-backward[:,:,1]*(1-fraction),cv2.INTER_LINEAR)
            premultiplied = wa*(1-fraction)+wb*fraction
            rgba = premultiplied.copy()
            rgba[:,:,:3] = np.divide(rgba[:,:,:3]*255,rgba[:,:,3:4],
                                     out=np.zeros_like(rgba[:,:,:3]),where=rgba[:,:,3:4]>0)
            tile = Image.fromarray(np.uint8(np.clip(rgba,0,255)))
            canvas = Image.new('RGBA',(840,720))
            canvas.paste(tile,(189,63))
            display = canvas.resize((560,480),Image.Resampling.LANCZOS)
            native = encode(stream,canvas)
            small = encode(stream,display,True)
            duration = round((number+1)*1000/60)-round(number*1000/60)
            record['animations']['dragging']['frames'].append({'ms':duration,'native':native,'display':small})
            visible = np.asarray(display).astype('float32')
            visible[:,:,:3] *= visible[:,:,3:4]/255
            if first is None:
                first = visible.copy()
                display.save(ROOT/'work'/'dragging-cutout.png')
            if last is not None:
                changes.append(float(np.abs(visible-last).mean()))
            last = visible
            if number % 30 == 0:
                preview.append(display)
            if number % 60 == 0:
                print('Interpolated output frame',number,'/',total,flush=True)
    record['data_bytes'] = (OUTPUT/'pet-frames.bin').stat().st_size
    (OUTPUT/'pet-frames.json').write_text(json.dumps(record,separators=(',',':'))+'\n',encoding='utf-8')
    metadata = {'version':1,'source_file':'64e08c4b4b4b2fe56386aa8dfe188c41.gif',
                'source_sha256':hashlib.sha256((LOCAL/'source.gif').read_bytes()).hexdigest(),
                'source_frames':len(frames),'source_duration_ms':2960,'output_frames':total,
                'duration_ms':sum(f['ms'] for f in record['animations']['dragging']['frames']),
                'fps':60,'canvas':record['canvas'],'display_canvas':record['display_canvas'],
                'layout_native_offset':[189,63],'bottom_edge_feather_pixels':24,
                'source_partial_framing_accepted':True,'original_gif_colours':True,
                'mask_reference':{'tool':'image_gen__imagegen','mode':'built-in',
                    'prompt':(LOCAL/'mask-prompt.txt').read_text(encoding='utf-8'),
                    'use':'Alpha reference only; animated colours are sampled from the original GIF.'},
                'files':{name:{'bytes':(OUTPUT/name).stat().st_size,'sha256':hashlib.sha256((OUTPUT/name).read_bytes()).hexdigest()}
                         for name in ('pet-frames.bin','pet-frames.json')}}
    (OUTPUT/'source.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
    report = dict(source_frames=len(frames),frames=total,fps=60,
                  loop_seam_difference=float(np.abs(last-first).mean()),
                  max_frame_difference=max(changes),median_frame_difference=float(np.median(changes)),
                  transparent_canvas_margin=True,source_partial_framing_accepted=True,
                  mask_reference_only_original_pixels_preserved=True)
    assert report['loop_seam_difference'] < max(changes)*1.15
    (ROOT/'work'/'dragging-asset-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    contact = Image.new('RGB',(3*280,2*240),'#eadfe7')
    for number,frame in enumerate(preview[:6]):
        tile = Image.new('RGBA',frame.size,'#eadfe7')
        tile.alpha_composite(frame)
        contact.paste(tile.convert('RGB').resize((280,240)),((number%3)*280,(number//3)*240))
    contact.save(ROOT/'work'/'dragging-contact.jpg')
    print(json.dumps(report,indent=2),flush=True)


if __name__ == '__main__':
    build()
