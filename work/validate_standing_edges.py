"""Check intact soles, removed floor pixels, and stable ribbon knots."""
from pathlib import Path
import json
import numpy as np
from PIL import Image,ImageSequence

root=Path(__file__).resolve().parent
def inspect(path):
    bottoms=[[],[]];floor_pixels=[];knot_areas=[[],[]];sole_areas=[[],[]]
    with Image.open(path) as im:
        for frame in ImageSequence.Iterator(im):
            alpha=np.array(frame.convert('RGBA').getchannel('A'))
            floor_pixels.append(int((alpha[660:700,375:450]>10).sum()+(alpha[669:710,480:560]>10).sum()))
            for foot,(x1,x2,y1,y2) in enumerate([(370,452,620,685),(480,560,630,695)]):
                yy=np.nonzero(alpha[y1:y2,x1:x2]>128)[0]
                bottoms[foot].append(int(yy.max()+y1))
            sole_areas[0].append(int((alpha[649:658,391:439]>128).sum()))
            sole_areas[1].append(int((alpha[657:667,489:543]>128).sum()))
            knot_areas[0].append(int((alpha[447:462,364:389]>128).sum()))
            knot_areas[1].append(int((alpha[450:468,514:540]>128).sum()))
    return {'frames':len(floor_pixels),'max_reflection_pixels':max(floor_pixels),'sole_bottom_range_pixels':[max(v)-min(v) for v in bottoms],'sole_bottom_minmax':[[min(v),max(v)]for v in bottoms],'minimum_sole_area':list(map(min,sole_areas)),'minimum_knot_area':list(map(min,knot_areas)),'knot_area_range':[[min(v),max(v)]for v in knot_areas]}

before=inspect(root.parent/'backups'/'before-standing-stabilization'/'assets'/'standing-obs.webp')
after=inspect(root/'repaired-assets'/'standing-obs.webp')
print('before',before,flush=True)
print('after',after,flush=True)
assert after['max_reflection_pixels']==0,'Floor reflection remains beneath a planted sole'
assert max(after['sole_bottom_range_pixels'])<=2,'Planted soles jump vertically'
assert min(after['minimum_sole_area'])>150,'A complete sole was cut off'
assert min(after['minimum_knot_area'])>35,'A pale ribbon knot disappeared'
(root/'standing-edge-validation.json').write_text(json.dumps({'before':before,'after':after},indent=2),encoding='utf-8')
