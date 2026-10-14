from pathlib import Path
import json
import numpy as np
from PIL import Image,ImageSequence
root=Path(__file__).resolve().parent
stage=root/'repaired-assets'
manifest=json.loads((stage/'manifest.json').read_text(encoding='utf-8'))
for name,spec in manifest['animations'].items():
    bad=[];extent=[600,630,0,0]
    with Image.open(stage/spec['file']) as im:
        for index,frame in enumerate(ImageSequence.Iterator(im)):
            rgba=frame.convert('RGBA');a=np.array(rgba.getchannel('A'))
            box=rgba.getbbox()
            extent=[min(extent[0],box[0]),min(extent[1],box[1]),max(extent[2],box[2]),max(extent[3],box[3])]
            if max(a[:6].max(),a[-6:].max(),a[:,:6].max(),a[:,-6:].max())>0:
                bad.append((index,box))
                if len(bad)<=3:
                    bg=Image.new('RGBA',rgba.size,'#30384c');bg.alpha_composite(rgba);bg.convert('RGB').save(root/('%s-border-%s.jpg'%(name,index)))
    print(name,'extent',extent,'bad',bad,flush=True)
