"""A reversible short fade and independent media clock for the grabbed pose."""
from PIL import Image


class DragMotion:
    FADE_SECONDS = .16

    def __init__(self):
        self.active = False
        self.weight = self.elapsed = 0.0
        self.held_frame = None
        self.entry_frame = None

    @property
    def visible(self):
        return self.active or self.weight > 0

    def start(self, frame, return_frame=None):
        if not self.visible:
            self.elapsed = 0
            self.entry_frame = frame
            self.held_frame = return_frame or frame
        self.active = True

    def stop(self):
        self.active = False

    def clear(self):
        self.active = False
        self.weight = self.elapsed = 0.0
        self.held_frame = self.entry_frame = None

    def advance(self, seconds):
        seconds = max(0,seconds)
        if self.visible:
            self.elapsed += seconds
        direction = 1 if self.active else -1
        self.weight = max(0,min(1,self.weight+direction*seconds/self.FADE_SECONDS))

    def blend(self, frame, size):
        base = self.entry_frame if self.active else self.held_frame
        return blend_frames(base or self.held_frame, frame, size, self.weight)


def blend_frames(base, frame, size, weight):
    if weight >= 1:
        return frame
    if weight <= 0:
        return base
    # Both inputs already contain premultiplied BGRA: blend those channels
    # directly, including alpha, so transparent edges never acquire a halo.
    layers = []
    for tile in (base,frame):
        layer = Image.new('RGBA',size)
        layer.paste(Image.frombytes('RGBA',tile['size'],tile['pixels'],'raw','BGRA'),tile['offset'])
        layers.append(layer)
    weight = weight*weight*(3-2*weight)
    mixed = Image.blend(*layers,weight)
    bounds = mixed.getbbox()
    tile = mixed.crop(bounds)
    return {'pixels':tile.tobytes('raw','BGRA'),'offset':bounds[:2],'size':tile.size}
