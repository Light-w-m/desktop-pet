"""Extract two original-video walk loops, matte, colour match and interpolate.

Generated images supply registered alpha only. Every RGB pixel is from the MP4.
Keep source frames, guides and caches local; publish checksums with the source.
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
sys.path.insert(0, str(ROOT/'work/sources/flow-deps'))
import cv2
import numpy as np
from PIL import Image, ImageDraw

LOCAL = ROOT/'local-media/walking-video'
OUTPUT = ROOT/'assets/walking'
VIDEO = Path('E:/DJI_video/10月17日.mp4')
SIZE = (736, 864)
FPS = 60
RANGES = {'left': (1.2, 3.4, 2.0), 'right': (10.7, 3.5, 12.0)}
cv2.setNumThreads(3)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def register(direction):
    rgb = np.asarray(Image.open(LOCAL/f'{direction}-guide-source.png').convert('RGB'))
    guide = np.asarray(Image.open(LOCAL/f'{direction}-guide.png').convert('RGBA'))
    sift = cv2.SIFT_create()
    a, da = sift.detectAndCompute(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), None)
    b, db = sift.detectAndCompute(cv2.cvtColor(guide, cv2.COLOR_RGBA2GRAY), None)
    matches = [x for x,y in cv2.BFMatcher().knnMatch(db,da,k=2) if x.distance < .72*y.distance]
    transform, accepted = cv2.estimateAffinePartial2D(
        np.float32([b[m.queryIdx].pt for m in matches]), np.float32([a[m.trainIdx].pt for m in matches]),
        method=cv2.RANSAC, ransacReprojThreshold=4)
    if transform is None or accepted.sum() < 25:
        raise ValueError('Walking alpha reference cannot register to original video')
    alpha = cv2.warpAffine(guide[:,:,3], transform, SIZE)
    Image.fromarray(alpha).save(LOCAL/f'{direction}-registered-alpha.png')
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), alpha, {
        'inliers': int(accepted.sum()), 'transform': transform.tolist(),
        'guide_name': direction, 'guide_sha256': digest(LOCAL/f'{direction}-guide.png')}


def matte(rgb, guide):
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    flow = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM).calc(gray, guide[0], None)
    yy,xx = np.mgrid[:SIZE[1],:SIZE[0]].astype('float32')
    prior = cv2.remap(guide[1], xx+flow[:,:,0], yy+flow[:,:,1], cv2.INTER_LINEAR)
    inside = (prior > 100).astype('uint8')
    core = cv2.erode(inside, np.ones((7,7),'uint8')) > 0
    outer = cv2.dilate(inside, np.ones((121,121),'uint8')) > 0
    labels = np.zeros(gray.shape,'uint8')
    labels[outer] = cv2.GC_PR_BGD
    labels[inside > 0] = cv2.GC_PR_FGD
    red,green,blue = rgb.astype('float32').transpose(2,0,1)
    pale = (red > green*.98) & (red > blue*.7) & (red > 95)
    # Shoes can swing farther than DIS can recover from a crossed-leg guide.
    # Grow around unambiguous original costume/skin colours as well as prior.
    recovered = cv2.dilate(pale.astype('uint8'),np.ones((25,25),'uint8')) > 0
    outer |= recovered
    labels[recovered & (labels == 0)] = cv2.GC_PR_BGD
    labels[outer & pale] = cv2.GC_PR_FGD
    labels[core] = cv2.GC_FGD
    # The room/floor is deep blue. Reject flow errors on that background,
    # while recovering bright legs/boots even outside the warped prior.
    labels[(red < blue*.58) & (red < 110)] = cv2.GC_BGD
    labels[outer & pale] = cv2.GC_FGD
    labels[(np.max(rgb,axis=2) < 28) & ~core] = cv2.GC_BGD
    cv2.grabCut(rgb, labels, None, np.zeros((1,65),'float64'), np.zeros((1,65),'float64'),
                4, cv2.GC_INIT_WITH_MASK)
    mask = np.isin(labels,(cv2.GC_FGD,cv2.GC_PR_FGD)).astype('uint8')
    count, components, stats, _ = cv2.connectedComponentsWithStats(mask)
    primary = 1+int(np.argmax(stats[1:,cv2.CC_STAT_AREA]))
    near = cv2.dilate((components == primary).astype('uint8'),np.ones((17,17),'uint8')) > 0
    keep = [primary]+[i for i in range(1,count) if stats[i,cv2.CC_STAT_AREA] >= 5 and
                     np.any((components == i) & near & (prior > 100))]
    selected = np.isin(components,keep).astype('uint8')
    selected = cv2.morphologyEx(selected,cv2.MORPH_CLOSE,np.ones((3,3),'uint8'))
    alpha = np.uint8(np.clip(cv2.GaussianBlur(selected.astype('float32'),(0,0),.5)*255+.5,0,255))
    return np.dstack((rgb,alpha))


def colour_curve(guide):
    source = np.asarray(Image.open(LOCAL/'left-guide-source.png').convert('RGB'))
    target = np.asarray(Image.open(ROOT/'assets/standing-obs.webp').convert('RGBA'))
    core = cv2.erode((guide[1] > 220).astype('uint8'),np.ones((7,7),'uint8')) > 0
    target_core = cv2.erode((target[:,:,3] > 220).astype('uint8'),np.ones((5,5),'uint8')) > 0
    q = (2,10,25,50,75,90,98)
    src = np.percentile(source[core],q,axis=0)
    dst = np.percentile(target[:,:,:3][target_core],q,axis=0)
    # One fixed curve shared by both directions; no pose-dependent exposure.
    curve = np.stack([np.interp(np.arange(256),np.r_[0,src[:,c],255],np.r_[0,dst[:,c],255])
                      for c in range(3)],axis=1)
    return np.uint8(np.clip(curve+.5,0,255)), {'percentiles':list(q),'source_rgb':src.tolist(),
        'standing_rgb':dst.tolist(),'standing_sha256':digest(ROOT/'assets/standing-obs.webp')}


def premultiply(rgba):
    value = rgba.astype('float32'); value[:,:,:3] *= value[:,:,3:4]/255
    return value


def straight(value):
    result = value.copy()
    result[:,:,:3] = np.divide(result[:,:,:3]*255,result[:,:,3:4],
        out=np.zeros_like(result[:,:,:3]),where=result[:,:,3:4] > .01)
    return Image.fromarray(np.uint8(np.clip(result,0,255)))


def encode(stream, image, display=False):
    box=image.getbbox(); tile=np.asarray(image.crop(box)).copy()
    if display:
        tile[:,:,:3]=tile[:,:,:3].astype('uint16')*tile[:,:,3:4]//255
        tile=tile[:,:,[2,1,0,3]]
    data=zlib.compress(tile.tobytes(),3)
    record=[stream.tell(),len(data),*box]; stream.write(data)
    return record


def build(extract=False, samples=False, reuse=False):
    LOCAL.mkdir(parents=True,exist_ok=True); OUTPUT.mkdir(parents=True,exist_ok=True)
    guides={direction:register(direction) for direction in (*RANGES,'left-cross','right-cross')}
    curve,colour_meta=colour_curve(guides['left'])
    loops={}; details={}
    for direction,(start,duration,_) in RANGES.items():
        folder=LOCAL/direction; folder.mkdir(exist_ok=True)
        if extract:
            subprocess.run(['ffmpeg','-v','error','-y','-ss',str(start),'-i',str(VIDEO),'-t',str(duration),
                '-vf','fps=60,crop=1840:2160:840:0,scale=736:864:flags=lanczos',str(folder/'frame-%03d.png')],check=True)
        raw=[np.asarray(Image.open(path).convert('RGB')) for path in sorted(folder.glob('frame-*.png'))]
        mask=cv2.dilate((guides[direction][1] > 128).astype('uint8'),np.ones((31,31),'uint8')) > 0
        starts=[0]+[i for i in range(1,len(raw)) if np.abs(raw[i].astype('int16')-raw[i-1])[mask].mean() > 1.0]
        groups=[(i,starts[k+1] if k+1 < len(starts) else len(raw)) for k,i in enumerate(starts)]
        if samples:
            groups=[groups[i] for i in np.linspace(0,len(groups)-1,8,dtype=int)]
        frames=[]; times=[]
        for a,b in groups:
            path=folder/f'matte-{a:03}.png'
            if reuse and path.is_file(): rgba=np.asarray(Image.open(path).convert('RGBA'))
            else:
                rgb=np.median(raw[a:b],axis=0).astype('uint8')
                # Select a stride or crossing guide by leg silhouette, not
                # time: each source segment contains several gait cycles.
                foreground=(rgb[:,:,0] > rgb[:,:,2].astype('float32')*.7) & (rgb[:,:,0] > 85)
                candidates=[guides[direction],guides[direction+'-cross']]
                guide=min(candidates,key=lambda g:np.logical_xor(foreground[510:825],g[1][510:825] > 128).sum())
                rgba=matte(rgb,guide)
                Image.fromarray(rgba).save(path)
            # Match normal standing head-to-sole height (~568 px), with fixed
            # placement for the entire cycle. Preserve original gait bobbing.
            rgb=np.stack([curve[rgba[:,:,c],c] for c in range(3)],axis=2).astype('float32')
            rgb += .45*np.clip(rgb-cv2.GaussianBlur(rgb,(0,0),.8),-10,10)
            adjusted=np.dstack((np.uint8(np.clip(rgb,0,255)),rgba[:,:,3]))
            scale,tx,ty=(.78,135,30) if direction == 'left' else (.83,90,25)
            transform=np.array([[scale,0,tx],[0,scale,ty]],'float32')
            canvas=cv2.warpAffine(premultiply(adjusted),transform,(840,720),flags=cv2.INTER_LANCZOS4)
            frames.append(canvas);times.append(a/60)
            straight(canvas).save(folder/f'stabilized-{a:03}.png')
            print(direction,a,b,flush=True)
        if samples:
            sheet=Image.new('RGBA',(1120,960),'#d6ccd2')
            for i,frame in enumerate(frames):
                im=straight(frame).resize((280,240),Image.Resampling.LANCZOS)
                sheet.alpha_composite(im,(i%4*280,i//4*480))
                dark=Image.new('RGBA',im.size,'#20242b');dark.alpha_composite(im)
                sheet.paste(dark,(i%4*280,i//4*480+240))
            sheet.convert('RGB').save(LOCAL/f'{direction}-samples.jpg')
            continue
        # Choose a full stride (same-leg phase), excluding startup acceleration.
        # Compare premultiplied character only; the moving room never matters.
        small=[cv2.resize(f,(210,180),interpolation=cv2.INTER_AREA) for f in frames]
        # Ignore codec-only updates between captured game poses. Interpolate
        # across the actual hold, rather than adding tiny stalls before it.
        retained=[0]
        for i in range(1,len(frames)):
            if np.abs(small[i]-small[retained[-1]]).mean() > .7:retained.append(i)
        frames=[frames[i] for i in retained];times=[times[i] for i in retained]
        small=[small[i] for i in retained];groups=[groups[i] for i in retained]
        candidates=[]
        for a in range(len(frames)):
            for b in range(a+1,len(frames)):
                period=times[b]-times[a]
                if .85 < period < 1.5:
                    score=np.abs(small[a]-small[b]).mean()
                    candidates.append((score,a,b))
        score,a,b=min(candidates)
        # Keep a true gait loop, interpolate the closure as another time pair.
        loops[direction]=(frames[a:b],np.array(times[a:b])-times[a],times[b]-times[a])
        details[direction]={'source_range_seconds':[start+times[a],start+times[b]],
            'distinct_source_frames':[x for x,y in groups[a:b]],'loop_score':float(score),
            'alpha_registration':guides[direction][2]}
    if samples:return
    index={'version':1,'canvas':[840,720],'display_canvas':[560,480],
           'data':'pet-frames.bin','animations':{}}
    tracker=cv2.optflow.createOptFlow_DeepFlow()
    yy,xx=np.mgrid[:720,:840].astype('float32')
    previews=[]
    with (OUTPUT/'pet-frames.bin').open('wb') as packed:
        for direction,(frames,times,duration) in loops.items():
            count=round(duration*FPS); records=[]; previous=None
            for number in range(count):
                t=number/FPS; pair=max(0,bisect_right(times,t)-1)
                following=(pair+1)%len(frames)
                end=times[following] if following else duration
                ratio=float((t-times[pair])/(end-times[pair]))
                if pair != previous:
                    a,b=frames[pair],frames[following]
                    ga,gb=(cv2.cvtColor(np.uint8(np.clip(v[:,:,:3],0,255)),cv2.COLOR_RGB2GRAY) for v in (a,b))
                    small_size=(420,360)
                    ga,gb=(cv2.resize(v,small_size,interpolation=cv2.INTER_AREA) for v in (ga,gb))
                    forward=cv2.resize(tracker.calc(ga,gb,None),(840,720))*2
                    backward=cv2.resize(tracker.calc(gb,ga,None),(840,720))*2
                    previous=pair
                wa=cv2.remap(a,xx-forward[:,:,0]*ratio,yy-forward[:,:,1]*ratio,cv2.INTER_LINEAR)
                wb=cv2.remap(b,xx-backward[:,:,0]*(1-ratio),yy-backward[:,:,1]*(1-ratio),cv2.INTER_LINEAR)
                mixed=wa*(1-ratio)+wb*ratio
                # Occluded boots can exist on only one side of the pair. A
                # plain dissolve turns them transparent. Preserve coverage
                # from the warped silhouettes, retaining soft outer edges.
                coverage=np.maximum(wa[:,:,3],wb[:,:,3])
                strength=min(1,4*min(ratio,1-ratio))
                alpha=mixed[:,:,3]+strength*(coverage-mixed[:,:,3])
                mixed[:,:,:3]=np.divide(mixed[:,:,:3],mixed[:,:,3:4],out=np.zeros_like(mixed[:,:,:3]),
                    where=mixed[:,:,3:4] > .01)*alpha[:,:,None]
                mixed[:,:,3]=alpha
                canvas=straight(mixed)
                display=canvas.resize((560,480),Image.Resampling.LANCZOS)
                records.append({'ms':round((number+1)*1000/FPS)-round(number*1000/FPS),
                    'native':encode(packed,canvas),'display':encode(packed,display,True)})
                if number in [round(i*count/4) for i in range(4)]:previews.append(display)
                if number==0:display.save(ROOT/f'work/walking-{direction}-cutout.png')
            index['animations']['walking_'+direction]={'frames':records}
            details[direction].update(output_frames=count,duration_ms=sum(r['ms'] for r in records))
    index['data_bytes']=(OUTPUT/'pet-frames.bin').stat().st_size
    (OUTPUT/'pet-frames.json').write_text(json.dumps(index,separators=(',',':'))+'\n',encoding='utf-8')
    meta={'version':1,'source_file':VIDEO.name,'source_sha256':digest(VIDEO),'source_fps':60,
        'crop':[840,0,1840,2160],'processing_size':list(SIZE),'output_fps':FPS,'directions':details,
        'colour_match':colour_meta,'interpolation':'bidirectional DeepFlow on premultiplied RGBA; occlusion-aware alpha coverage; periodic stride closure',
        'fixed_placement':{'left':[[.78,0,135],[0,.78,30]],'right':[[.83,0,90],[0,.83,25]]},
        'alpha_references':{'tool':'image_gen__imagegen','mode':'built-in','prompt':(LOCAL/'mask-prompt.txt').read_text(encoding='utf-8'),
            'registrations':{name:guide[2] for name,guide in guides.items()},
            'use':'registered alpha only; all animated RGB from original video'},
        'files':{name:{'bytes':(OUTPUT/name).stat().st_size,'sha256':digest(OUTPUT/name)} for name in ('pet-frames.bin','pet-frames.json')}}
    (OUTPUT/'source.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    sheet=Image.new('RGBA',(1120,240*((len(previews)+3)//4)),'#e7dce4')
    for i,im in enumerate(previews):sheet.alpha_composite(im.resize((280,240)),(i%4*280,i//4*240))
    sheet.convert('RGB').save(ROOT/'work/walking-contact.jpg')
    print(json.dumps(details),flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extract',action='store_true');parser.add_argument('--samples',action='store_true')
    parser.add_argument('--reuse-mattes',action='store_true');args=parser.parse_args()
    build(args.extract,args.samples,args.reuse_mattes)
