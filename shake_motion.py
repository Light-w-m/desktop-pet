"""Recognize deliberate back-and-forth dragging and play one stomp reaction."""
from collections import deque
import math

from drag_motion import DragMotion, blend_frames


class ShakeDetector:
    WINDOW_SECONDS = 1.25
    IDLE_SECONDS = .24

    def __init__(self):
        self.cancel()

    def cancel(self):
        self.points = deque(maxlen=160)
        self.last_motion = None
        self.armed = self.used = False
        self.scale = 1.0

    def begin(self, x, y, now, scale=1.0):
        self.cancel()
        self.scale = scale
        self.points.append((now, x, y))
        self.last_motion = now

    def record(self, x, y, now):
        if self.used or not self.points:
            return
        previous = self.points[-1]
        if now-previous[0] < .008 or math.hypot(x-previous[1], y-previous[2]) < 3:
            return
        self.last_motion = now
        self.points.append((now, x, y))
        while self.points and now-self.points[0][0] > self.WINDOW_SECONDS:
            self.points.popleft()
        if self.armed or len(self.points) < 6 or now-self.points[0][0] < .28:
            return
        travel = sum(math.hypot(b[1]-a[1], b[2]-a[2]) for a, b in zip(self.points, list(self.points)[1:]))
        if travel < max(140, 200*self.scale):
            return
        threshold = max(14, 24*self.scale)
        for axis in (1, 2):
            values = [point[axis] for point in self.points]
            if max(values)-min(values) < max(36, 52*self.scale):
                continue
            direction, extreme, turns = 0, values[0], 0
            for value in values[1:]:
                if direction == 0:
                    if abs(value-extreme) >= threshold:
                        direction = 1 if value > extreme else -1
                        extreme = value
                elif (value-extreme)*direction >= 0:
                    extreme = value
                elif abs(value-extreme) >= threshold:
                    direction = -direction
                    extreme = value
                    turns += 1
            if turns >= 4:
                self.armed = True
                return

    def idle(self, now):
        return self.armed and not self.used and now-self.last_motion >= self.IDLE_SECONDS

    def consume(self, now):
        trigger = self.armed and not self.used and now-self.last_motion <= .8
        self.armed = False
        self.used = True
        return trigger


class StompMotion(DragMotion):
    FADE_IN = .12
    FADE_OUT = .18

    def start_once(self, entry_frame, return_frame, duration):
        self.clear()
        self.duration = duration
        self.start(entry_frame, return_frame)

    def advance(self, seconds):
        if not self.visible:
            return
        self.elapsed = min(self.duration, self.elapsed+max(0, seconds))
        self.weight = max(0, min(1, self.elapsed/self.FADE_IN,
                                 (self.duration-self.elapsed)/self.FADE_OUT))
        self.active = self.elapsed < self.duration

    def blend(self, frame, size):
        base = self.entry_frame if self.elapsed < self.FADE_IN else self.held_frame
        return blend_frames(base or self.held_frame, frame, size, self.weight)
