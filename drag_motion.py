"""A reversible short fade and independent media clock for the grabbed pose."""
from PIL import Image


class DragMotion:
    FADE_SECONDS = .16

    def __init__(self):
        self.active = False
        self.weight = self.elapsed = 0.0
        self.held_frame = None

    @property
    def visible(self):
        return self.active or self.weight > 0

    def start(self, frame):
        if not self.visible:
            self.elapsed = 0
            self.held_frame = frame
        self.active = True

    def stop(self):
        self.active = False

    def advance(self, seconds):
        seconds = max(0,seconds)
        if self.visible:
            self.elapsed += seconds
        direction = 1 if self.active else -1
        self.weight = max(0,min(1,self.weight+direction*seconds/self.FADE_SECONDS))

    def blend(self, frame, size):
        if self.weight >= 1:
            return frame
        if self.weight <= 0:
            return self.held_frame
        # Both inputs already contain premultiplied BGRA: blend those channels
        # directly, including alpha, so transparent edges never acquire a halo.
        layers = []
        for tile in (self.held_frame,frame):
            layer = Image.new('RGBA',size)
            layer.paste(Image.frombytes('RGBA',tile['size'],tile['pixels'],'raw','BGRA'),tile['offset'])
            layers.append(layer)
        weight = self.weight*self.weight*(3-2*self.weight)
        mixed = Image.blend(*layers,weight)
        bounds = mixed.getbbox()
        tile = mixed.crop(bounds)
        return {'pixels':tile.tobytes('raw','BGRA'),'offset':bounds[:2],'size':tile.size}
