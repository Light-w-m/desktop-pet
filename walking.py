"""Horizontal roaming and sparse, completion-driven ascension speech."""
import random

class WalkingMotion:
    SPEED = 58.0  # Default display pixels/sec; follows the scale of the gait.
    FADE = .12
    TURN = 0.0

    def __init__(self):
        self.active = self.preparing = False
        self.weight = self.elapsed = self.turn_elapsed = 0.0
        self.entry_frame = self.turn_frame = None
        self.x = self.y = 0
        self.direction = -1
        self.turn_duration = 0.0
        self.turning = False

    @property
    def visible(self):
        return self.active or self.weight > 0

    @property
    def name(self):
        if self.turning:return 'walking_turn' if self.direction>0 else 'walking_turn_back'
        return 'walking_left' if self.direction < 0 else 'walking_right'

    def start(self, x, y, limits, scale, frame):
        self.left, self.right = sorted(limits)
        self.x = max(self.left,min(x,self.right))
        self.y = y
        self.speed = self.SPEED*scale
        self.direction = 1 if self.x <= self.left else -1
        self.elapsed = self.weight = 0.0
        self.turn_elapsed = self.TURN
        self.entry_frame, self.turn_frame = frame, None
        self.active = self.preparing = True
        self.turning = False

    def stop(self):
        self.active = self.preparing = False

    def clear(self):
        self.stop()
        self.weight = 0.0
        self.entry_frame = self.turn_frame = None
        self.turning = False

    def advance(self, seconds):
        seconds = max(0,seconds)
        if self.preparing:
            return False
        self.weight = max(0,min(1,self.weight+(1 if self.active else -1)*seconds/self.FADE))
        self.elapsed += seconds
        self.turn_elapsed += seconds
        if not self.active:
            return False
        if self.turn_duration > 0:
            if self.turning:
                if self.elapsed >= self.turn_duration:
                    self.elapsed -= self.turn_duration
                    self.turning = False
                return False
            distance=self.x-self.left if self.direction<0 else self.right-self.x
            if self.speed*seconds >= distance:
                self.x=self.left if self.direction<0 else self.right
                self.direction *= -1
                self.turning = True
                self.elapsed = 0.0
                return True
            self.x += self.direction*self.speed*seconds
            return False
        span = self.right-self.left
        if span <= 0:
            return False
        old_direction = self.direction
        # Unfold then fold the path. Even a delayed tick cannot cross an edge.
        position = self.x-self.left if self.direction > 0 else 2*span-(self.x-self.left)
        position = (position+self.speed*seconds) % (2*span)
        self.x = self.left+(position if position < span else 2*span-position)
        self.direction = 1 if position < span else -1
        if self.direction != old_direction:
            self.elapsed = 0.0
            self.turn_elapsed = 0.0
            return True
        return False

    def blend(self, frame, size, return_frame):
        # A single pose per draw, including transitions. Never dissolve two
        # silhouettes into the double legs/arms seen in the previous version.
        if self.weight >= 1:return frame
        base = self.entry_frame if self.active else return_frame
        if self.weight < .5:
            chosen,opacity=base or return_frame,1-2*self.weight
        else:
            chosen,opacity=frame,2*self.weight-1
        table=bytes(round(i*opacity) for i in range(256))
        return dict(chosen,pixels=chosen['pixels'].translate(table))


class WalkingSpeech:
    TITLES = tuple('突破的感受·'+suffix for suffix in ('起','承','转','合'))
    GAP = .8

    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.restart()

    def restart(self):
        self.index = None
        self.playing_id = None
        self.remaining = self.rng.uniform(25,40)

    def defer(self):
        self.index = self.playing_id = None
        self.remaining = self.rng.uniform(90,150)

    def owns(self, identifier):
        return self.playing_id is not None and identifier == self.playing_id

    def started(self, identifier):
        self.playing_id = identifier

    def advance(self, seconds, current_id, available, *, enabled=True, busy=False):
        if not enabled:
            if self.index is not None:self.defer()
            return None
        if self.playing_id is not None:
            if current_id == self.playing_id:
                return None  # Wait for the actual device completion.
            if current_id is not None:
                self.defer()
                return None
            self.playing_id = None
            self.index += 1
            if self.index >= len(self.TITLES):
                self.defer()
            else:
                self.remaining = self.GAP
            return None  # The completion tick never consumes any of the gap.
        if busy or current_id is not None:
            if self.index is not None:self.defer()
            return None
        self.remaining -= min(max(0,seconds),1.0)
        if self.remaining > 1e-9:
            return None
        if not all(title in available for title in self.TITLES):
            self.defer()
            return None
        if self.index is None:self.index = 0
        return self.TITLES[self.index]
