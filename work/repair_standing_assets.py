"""Fix standing outlines and the shared standing starts/returns of every pose."""
from pathlib import Path
import json
import subprocess
import shutil
import cv2
from PIL import Image,ImageSequence
from extract_obs import SOURCES,layout,mix,CANVAS
from standing_matte import StandingMatte,reference_from_video

root=Path(__file__).resolve().parent.parent
stage=root/'work'/'repaired-assets'
manifest=json.loads((root/'assets'/'manifest.json').read_text(encoding='utf-8'))
backup=root/'backups'/'before-standing-stabilization'
(backup/'assets').mkdir(parents=True,exist_ok=True)
for name in ['manifest.json']+[spec['file'] for spec in manifest['animations'].values()]:
    if not (backup/'assets'/name).exists():shutil.copy2(root/'assets'/name,backup/'assets'/name)
if not (backup/'CitlaliDesktopPet.exe').exists():shutil.copy2(root/'CitlaliDesktopPet.exe',backup/'CitlaliDesktopPet.exe')
repair=StandingMatte(reference_from_video())
captures={};next_frame={}
def repaired(name,index):
    path,start,end=SOURCES[name]
    if name not in captures:
        captures[name]=cv2.VideoCapture(str(path));next_frame[name]=-1
    cap=captures[name];wanted=round(start*60)+index
    if wanted!=next_frame[name]:cap.set(cv2.CAP_PROP_POS_FRAMES,wanted)
    ok,bgr=cap.read()
    if not ok:raise RuntimeError('Missing source frame')
    next_frame[name]=wanted+1
    return layout(repair.apply(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)))

canonical=repaired('standing',0)
for name,spec in manifest['animations'].items():
    count=spec['frames'];bridge=12
    process=subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgba','-s','840x720','-framerate','60','-i','pipe:0','-an','-c:v','libwebp_anim','-lossless','1','-compression_level','0','-loop','0',str(stage/spec['file'])],stdin=subprocess.PIPE)
    with Image.open(root/'assets'/spec['file']) as im:
        for index,frame in enumerate(ImageSequence.Iterator(im)):
            if name=='standing' or index<bridge or index>=count-bridge:
                pose=repaired(name,index)
                if index<bridge:pose=mix(canonical,pose,index/(bridge-1))
                if index>=count-bridge:pose=mix(pose,canonical,(index-(count-bridge))/(bridge-1))
            else:pose=frame.convert('RGBA')
            process.stdin.write(pose.tobytes())
    process.stdin.close()
    if process.wait():raise RuntimeError('Encode failed: '+name)
    spec['standing_contours_repaired']=True
    print('Repaired',name,flush=True)
for cap in captures.values():cap.release()
manifest['version']=5
manifest['standing_matting']={'floor_reflection_removed':True,'shoe_outlines':'tracked planted sole contours','ribbons':'tracked full tails and pale knots','shared_standing_endpoints_repaired':True}
(stage/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
