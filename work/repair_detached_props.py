"""Restore recorded cushion spawn/shrink frames without altering other poses."""
from pathlib import Path
import json
import subprocess
import sys
import cv2
from PIL import Image,ImageSequence
from extract_obs import SOURCES,CANVAS,layout
from matte_obs import CROP,matte

root=Path(__file__).resolve().parent
stage=root/'repaired-assets'
manifest=json.loads((stage/'manifest.json').read_text(encoding='utf-8'))
assert manifest['canvas'] in ([630,720],[840,720])
ranges={'reading':[(12,180)]} if '--reading-entry' in sys.argv else {'standing':[],'reading':[(12,180),(630,780)],'drinking':[(15,95),(800,900)]}
for name,windows in ranges.items():
    spec=manifest['animations'][name]
    path=stage/spec['file'];target=path.with_name(name+'-props.webp')
    source,start,end=SOURCES[name]
    cap=cv2.VideoCapture(str(source));next_source=-1
    process=subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgba','-s','840x720','-framerate','60','-i','pipe:0','-an','-c:v','libwebp_anim','-lossless','1','-compression_level','0','-loop','0',str(target)],stdin=subprocess.PIPE)
    count=0
    with Image.open(path) as im:
        for index,frame in enumerate(ImageSequence.Iterator(im)):
            if any(a<=index<b for a,b in windows):
                source_index=round(start*60)+index
                if source_index!=next_source:cap.set(cv2.CAP_PROP_POS_FRAMES,source_index)
                ok,bgr=cap.read()
                if not ok:raise RuntimeError('Missing recording frame')
                next_source=source_index+1
                x1,y1,x2,y2=CROP
                pose=layout(matte(cv2.cvtColor(bgr[y1:y2,x1:x2],cv2.COLOR_BGR2RGB)))
                count+=1
            else:
                pose=Image.new('RGBA',CANVAS)
                pose.paste(frame.convert('RGBA'),((CANVAS[0]-frame.width)//2,0))
            process.stdin.write(pose.tobytes())
    cap.release();process.stdin.close()
    if process.wait():raise RuntimeError('Prop repair encoding failed')
    target.replace(path)
    print(name,'restored',count,'spawn/return frames',flush=True)
manifest['canvas']=list(CANVAS)
manifest['display_canvas']=[560,480]
manifest['coverage']='Full character and cushion with detached spawn/shrink frames and sideways return travel; common standing endpoints and shared original proportions.'
(stage/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
