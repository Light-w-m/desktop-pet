"""Add side margins to the existing extraction without resampling pixels."""
from pathlib import Path
import json
import subprocess
from PIL import Image,ImageSequence

root=Path(__file__).resolve().parent
stage=root/'repaired-assets'
manifest=json.loads((stage/'manifest.json').read_text(encoding='utf-8'))
assert manifest['canvas']==[600,720]
for name,spec in manifest['animations'].items():
    path=stage/spec['file']
    target=path.with_name(name+'-padded.webp')
    process=subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgba','-s','630x720','-framerate','60','-i','pipe:0','-an','-c:v','libwebp_anim','-lossless','1','-compression_level','0','-loop','0',str(target)],stdin=subprocess.PIPE)
    sheet=Image.new('RGB',(420*5,480),'#1e212c')
    count=spec['frames']
    samples={0:0,count//4:1,count//2:2,3*count//4:3,count-1:4}
    with Image.open(path) as im:
        for index,frame in enumerate(ImageSequence.Iterator(im)):
            pose=Image.new('RGBA',(630,720))
            pose.paste(frame.convert('RGBA'),(15,0))
            process.stdin.write(pose.tobytes())
            if index in samples:
                thumb=pose.resize((420,480),Image.Resampling.LANCZOS)
                sheet.paste(thumb,(samples[index]*420,0),thumb)
    process.stdin.close()
    if process.wait():raise RuntimeError('Padding encode failed: '+name)
    target.replace(path)
    sheet.save(root/(name+'-obs-qa.jpg'),quality=96)
    print('Padded',name,flush=True)
manifest['canvas']=[630,720]
manifest['display_canvas']=[420,480]
(stage/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
