"""Matte and stabilize the user's MP4, then interpolate one reaction to 60 FPS.

Imagegen supplies alpha guides only. SIFT registers them back onto the original
pixels; every animated color comes from the video, with restrained sharpening.
Raw videos, guides and diagnostic frames stay in ignored local-media.
"""
from bisect import bisect_right
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zlib

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT/'work/sources/drag-deps'))
import cv2
import numpy as np
from PIL import Image, ImageDraw

LOCAL = ROOT/'local-media/stomp-video'
OUTPUT = ROOT/'assets/stomping'
VIDEO = Path('E:/DJI_video/8790CBFF-D122-4739-9F87-A955A3C94149.mp4')
SIZE = (736, 864)
START = 10/120
DURATION = 2.35
CLIP_START = 63  # Skip the burst's two-hand reach; keep only the foot reaction.
FPS = 60
GUIDES = (1, 33, 82, 136)
cv2.setNumThreads(3)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def register_guide(number):
    rgb = np.asarray(Image.open(LOCAL/f'frame-{number:03}.png').convert('RGB'))
    guide = np.asarray(Image.open(LOCAL/f'guide-{number:03}.png').convert('RGBA'))
    sift = cv2.SIFT_create()
    a, da = sift.detectAndCompute(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), None)
    b, db = sift.detectAndCompute(cv2.cvtColor(guide, cv2.COLOR_RGBA2GRAY), None)
    matches = [x for x,y in cv2.BFMatcher().knnMatch(db,da,k=2) if x.distance < .72*y.distance]
    transform, accepted = cv2.estimateAffinePartial2D(
        np.float32([b[m.queryIdx].pt for m in matches]), np.float32([a[m.trainIdx].pt for m in matches]),
        method=cv2.RANSAC, ransacReprojThreshold=5)
    if transform is None or accepted.sum() < 30:
        raise ValueError('Alpha reference does not register to the video')
    alpha = cv2.warpAffine(guide[:,:,3], transform, SIZE)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), alpha, {
        'source_frame':number, 'inliers':int(accepted.sum()), 'transform':transform.tolist(),
        'guide_sha256':digest(LOCAL/f'guide-{number:03}.png')}


def matte(rgb, guide):
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    reference, alpha, _ = guide
    flow = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM).calc(gray,reference,None)
    yy,xx = np.mgrid[:SIZE[1],:SIZE[0]].astype('float32')
    prior = cv2.remap(alpha,xx+flow[:,:,0],yy+flow[:,:,1],cv2.INTER_LINEAR)
    inside = (prior > 110).astype('uint8')
    core = cv2.erode(inside,np.ones((7,7),'uint8')) > 0
    # Allow a moving boot or lowered hand to leave the optical-flow prior.
    # Pale skin/costume seeds distinguish it from this dark blue scene.
    outer = cv2.dilate(inside,np.ones((91,91),'uint8')) > 0
    labels = np.zeros(gray.shape,'uint8')
    labels[outer] = cv2.GC_PR_BGD
    labels[inside > 0] = cv2.GC_PR_FGD
    red,green,blue=rgb.astype('float32').transpose(2,0,1)
    pale=(red > green*.95) & (red > blue*.65) & (np.max(rgb,axis=2) > 110)
    labels[outer & pale] = cv2.GC_PR_FGD
    labels[core] = cv2.GC_FGD
    # Very dark scene pixels should not attach to skirts or fill limb gaps.
    labels[(np.max(rgb,axis=2) < 45) & ~core] = cv2.GC_BGD
    labels[np.max(rgb,axis=2) < 28] = cv2.GC_BGD
    yy=np.arange(rgb.shape[0])[:,None]
    cyan=(green > red*1.3+12) & (blue > red*1.3+12) & (green > 100)
    magenta=(red > green*1.8+10) & (blue > green*1.8+10) & (blue > 100)
    effect=(cyan | magenta) & (yy > 520)
    # Reject the star/glowing lines beyond the registered boot contour while
    # preserving the body underneath the effect for subsequent RGB repair.
    labels[effect & (prior < 150)] = cv2.GC_BGD
    labels[effect & (prior >= 150)] = cv2.GC_FGD
    cv2.grabCut(rgb,labels,None,np.zeros((1,65),'float64'),np.zeros((1,65),'float64'),4,cv2.GC_INIT_WITH_MASK)
    mask = np.isin(labels,(cv2.GC_FGD,cv2.GC_PR_FGD)).astype('uint8')
    count,components,stats,_ = cv2.connectedComponentsWithStats(mask)
    primary = 1+int(np.argmax(stats[1:,cv2.CC_STAT_AREA]))
    near = cv2.dilate((components == primary).astype('uint8'),np.ones((13,13),'uint8')) > 0
    keep = [primary]+[i for i in range(1,count) if i != primary and stats[i,cv2.CC_STAT_AREA] >= 5
                     and np.any((components == i) & near & (prior > 128))]
    selected=cv2.morphologyEx(np.isin(components,keep).astype('uint8'),cv2.MORPH_CLOSE,np.ones((3,3),'uint8'))
    # Screen-space light strokes can also be white. Remove only narrow
    # horizontal/vertical extensions that lie outside the tracked silhouette.
    distance=cv2.distanceTransform(selected,cv2.DIST_L2,3)
    extensions=(prior < 60) & (distance < 2.5)
    selected[extensions & (cv2.GaussianBlur(prior,(0,0),2) < 45)] = 0
    # A persistent purple HUD glyph sits immediately behind the left hand.
    # In that local area the registered hand outline is the reliable boundary.
    xx=np.arange(rgb.shape[1])[None,:]
    hand_zone=(xx < 155) & (yy > 230) & (yy < 475)
    hand_outline=cv2.dilate((prior > 100).astype('uint8'),np.ones((5,5),'uint8')) > 0
    selected[hand_zone & ~hand_outline] = 0
    alpha = cv2.GaussianBlur(selected.astype('float32'),(0,0),.55)
    return np.dstack((rgb,np.uint8(np.clip(alpha*255+.5,0,255))))


def standing_colour_curve(guide):
    """One fixed per-channel curve, calibrated against the normal idle.

    Use opaque character pixels from a recovered video stance and the real
    standing asset. Fixed quantiles avoid per-frame auto-exposure flicker.
    """
    reference=ROOT/'assets/standing-obs.webp'
    target=np.asarray(Image.open(reference).convert('RGBA'))
    original=np.asarray(Image.open(LOCAL/'frame-136.png').convert('RGB'))
    target_core=cv2.erode((target[:,:,3] > 220).astype('uint8'),np.ones((5,5),'uint8')) > 0
    source_core=cv2.erode((guide[1] > 220).astype('uint8'),np.ones((7,7),'uint8')) > 0
    percentiles=(2,10,25,50,75,90,98)
    source_values=np.percentile(original[source_core],percentiles,axis=0)
    target_values=np.percentile(target[:,:,:3][target_core],percentiles,axis=0)
    curves=[]
    for channel in range(3):
        x=np.r_[0,source_values[:,channel],255]
        y=np.r_[0,target_values[:,channel],255]
        unique=np.r_[True,np.diff(x) > 0]
        curves.append(np.uint8(np.clip(np.interp(np.arange(256),x[unique],y[unique])+.5,0,255)))
    return curves,{'reference':'assets/standing-obs.webp','reference_sha256':digest(reference),
        'source_frame':136,'percentiles':list(percentiles),'source_rgb':source_values.tolist(),
        'standing_rgb':target_values.tolist(),'fixed_across_all_frames':True}


def remove_light(rgba, curves):
    rgb = rgba[:,:,:3].copy()
    # Cyan streaks are screen-space effects, not costume details. Reconstruct
    # the narrow occluded stripes from the adjacent original video pixels.
    red,green,blue=rgb.astype('float32').transpose(2,0,1)
    effect = ((((green > red*1.25+10) & (blue > red*1.25+10) & (green > 100)) |
               ((red > green*1.8+10) & (blue > green*1.8+10) & (blue > 100))) & (rgba[:,:,3] > 100))
    # Preserve the turquoise chest pendant. Effects occur below the skirt.
    effect[:480] = False
    if effect.any():
        mask = cv2.dilate(effect.astype('uint8'),np.ones((3,3),'uint8'))
        rgb = cv2.inpaint(rgb,mask,5,cv2.INPAINT_TELEA)
    # Match the normal standing palette instead of merely brightening the
    # night recording by a fixed gain. Keep alpha and outline shadows intact.
    values=np.stack([curves[c][rgb[:,:,c]] for c in range(3)],axis=2).astype('float32')/255
    detail = values-cv2.GaussianBlur(values,(0,0),1.0)
    values = np.clip(values+.6*np.clip(detail,-.055,.055),0,1)
    rgba[:,:,:3] = np.uint8(values*255+.5)
    rgba[rgba[:,:,3] == 0,:3] = 0
    return rgba


def premultiply(rgba):
    value = rgba.astype('float32')
    value[:,:,:3] *= value[:,:,3:4]/255
    return value


def straight(value):
    value=value.copy()
    value[:,:,:3] = np.divide(value[:,:,:3]*255,value[:,:,3:4],
        out=np.zeros_like(value[:,:,:3]),where=value[:,:,3:4] > .01)
    return Image.fromarray(np.uint8(np.clip(value,0,255)))


def encode(stream,image,premultiplied=False):
    bounds = image.getbbox()
    tile = np.asarray(image.crop(bounds)).copy()
    if premultiplied:
        tile[:,:,:3] = tile[:,:,:3].astype('uint16')*tile[:,:,3:4]//255
        tile = tile[:,:,[2,1,0,3]]
    data=zlib.compress(tile.tobytes(),3)
    record=[stream.tell(),len(data),*bounds]
    stream.write(data)
    return record


def build(extract=False, reuse_mattes=False):
    LOCAL.mkdir(parents=True,exist_ok=True)
    OUTPUT.mkdir(parents=True,exist_ok=True)
    if extract:
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-ss',str(START),'-i',str(VIDEO),
            '-t',str(DURATION),'-vf','fps=60,crop=1840:2160:840:0,scale=736:864:flags=lanczos',
            '-y',str(LOCAL/'frame-%03d.png')],check=True)
    guides={n:register_guide(n) for n in GUIDES}
    curves,colour_metadata=standing_colour_curve(guides[136])
    raw=[np.asarray(Image.open(LOCAL/f'frame-{i+1:03}.png').convert('RGB')) for i in range(round(DURATION*FPS))]
    # Detect captured holds instead of treating 120 FPS screen capture as
    # 120 distinct animation poses. Ignore sub-pixel compression noise.
    starts=[0]+[i for i in range(1,len(raw)) if np.abs(raw[i].astype('int16')-raw[i-1]).mean() > 1.5]
    groups=[(i,(starts[k+1] if k+1 < len(starts) else len(raw))) for k,i in enumerate(starts)]
    groups=[(start,end) for start,end in groups if end > CLIP_START]
    rgbs=[np.median(raw[start:end],axis=0).astype('uint8') for start,end in groups]
    mattes=[]
    for (start,end),rgb in zip(groups,rgbs):
        nearest=min(GUIDES,key=lambda n:abs(n-1-start))
        cached=LOCAL/f'matte-{start:03}.png'
        rgba=np.asarray(Image.open(cached).convert('RGBA')) if reuse_mattes and cached.exists() else matte(rgb,guides[nearest])
        Image.fromarray(rgba).save(LOCAL/f'matte-{start:03}.png')
        mattes.append(rgba)
        print(f'Matted video pose {start}/{len(raw)}',flush=True)
    frames=[]
    # Standing origin is shared with the normal idle: head about y=98,
    # planted soles y=666, torso around x=445 on the 840x720 native canvas.
    # Calibrate against the recovered upright pose, not the shorter crouch.
    # A fixed transform preserves the real crouch/jump and prevents per-frame
    # bounding-box normalization from making the body grow or feet swim.
    placement=np.array([[.76,0,209],[0,.76,37]],'float32')
    for i,rgba in enumerate(mattes):
        adjusted=remove_light(rgba.copy(),curves)
        canvas=cv2.warpAffine(premultiply(adjusted),placement,(840,720),flags=cv2.INTER_LANCZOS4)
        frames.append(canvas)
        straight(canvas).save(LOCAL/f'stabilized-{i:03}.png')
    times=np.array([start for start,end in groups],dtype='float64')/FPS
    tracker=cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    yy,xx=np.mgrid[:720,:840].astype('float32')
    index={'version':1,'canvas':[840,720],'display_canvas':[560,480],
           'data':'pet-frames.bin','animations':{'stomping':{'frames':[]}}}
    previews=[]
    previous=None
    count=len(raw)-CLIP_START
    temporary=OUTPUT/'pet-frames.part.bin'
    with temporary.open('wb') as packed:
        for number in range(count):
            t=(number+CLIP_START)/FPS
            pair=min(bisect_right(times,t)-1,len(frames)-1)
            following=min(pair+1,len(frames)-1)
            ratio=float((t-times[pair])/(times[following]-times[pair])) if following != pair else 0
            if pair != previous:
                a,b=frames[pair],frames[following]
                ga,gb=(cv2.cvtColor(np.uint8(np.clip(v[:,:,:3],0,255)),cv2.COLOR_RGB2GRAY) for v in (a,b))
                forward=tracker.calc(ga,gb,None)
                backward=tracker.calc(gb,ga,None)
                previous=pair
            wa=cv2.remap(a,xx-forward[:,:,0]*ratio,yy-forward[:,:,1]*ratio,cv2.INTER_LINEAR)
            wb=cv2.remap(b,xx-backward[:,:,0]*(1-ratio),yy-backward[:,:,1]*(1-ratio),cv2.INTER_LINEAR)
            canvas=straight(wa*(1-ratio)+wb*ratio)
            display=canvas.resize((560,480),Image.Resampling.LANCZOS)
            index['animations']['stomping']['frames'].append({'ms':round((number+1)*1000/FPS)-round(number*1000/FPS),
                'native':encode(packed,canvas),'display':encode(packed,display,True)})
            if number in (0,12,24,36,54,count-1):
                previews.append(display)
            if number == 0:display.save(ROOT/'work/stomping-cutout.png')
    temporary.replace(OUTPUT/'pet-frames.bin')
    index['data_bytes']=(OUTPUT/'pet-frames.bin').stat().st_size
    (OUTPUT/'pet-frames.json').write_text(json.dumps(index,separators=(',',':'))+'\n',encoding='utf-8')
    metadata={'version':2,'source_file':VIDEO.name,'source_sha256':digest(VIDEO),
        'source_video':{'width':3840,'height':2160,'fps':120,'frames':728},
        'source_range_seconds':[START+CLIP_START/FPS,START+DURATION],'decoded_crop':[840,0,1840,2160],
        'processing_size':list(SIZE),'distinct_pose_frames':[start for start,end in groups],
        'discarded_intro_frames':CLIP_START,'output_frames':count,
        'duration_ms':sum(f['ms'] for f in index['animations']['stomping']['frames']),'fps':FPS,'canvas':index['canvas'],
        'display_canvas':index['display_canvas'],'one_shot':True,'return_pose':'standing',
        'sequence':['stomp','settle_to_standing'],'colour_match':colour_metadata,
        'processing':{'colors':'original video; fixed monotone RGB curves matched to standing; bounded unsharp .6 at sigma 1',
            'matting':'registered alpha guides, dense optical flow, seeded GrabCut',
            'stabilization':'fixed similarity calibrated to upright body size and standing baseline; preserve crouch and jump',
            'interpolation':'bidirectional optical flow on premultiplied RGBA at original timestamps',
            'light_cleanup':'cyan effects below skirt only, local adjacent pixel reconstruction'},
        'alpha_references':{'tool':'image_gen__imagegen','mode':'built-in',
            'prompt':(LOCAL/'mask-prompt.txt').read_text(encoding='utf-8'),
            'use':'Only registered alpha guidance; generated RGB never enters the animation.',
            'registrations':[guides[n][2] for n in GUIDES]},
        'layout_native_transform':placement.tolist(),
        'files':{name:{'bytes':(OUTPUT/name).stat().st_size,'sha256':digest(OUTPUT/name)}
                 for name in ('pet-frames.bin','pet-frames.json')}}
    (OUTPUT/'source.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
    contact=Image.new('RGB',(840,480),'#eadfe7')
    for i,frame in enumerate(previews):
        bg=Image.new('RGBA',frame.size,'#eadfe7');bg.alpha_composite(frame)
        contact.paste(bg.convert('RGB').resize((280,240)),((i%3)*280,(i//3)*240))
    contact.save(ROOT/'work/stomping-contact.jpg')
    print(json.dumps({'frames':count,'poses':len(groups),'bytes':index['data_bytes']}),flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extract',action='store_true')
    parser.add_argument('--reuse-mattes',action='store_true',help='Reuse local matte diagnostics during QA iterations')
    args=parser.parse_args()
    build(args.extract,args.reuse_mattes)
