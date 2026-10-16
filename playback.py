"""Media clock that switches only at a recorded standing boundary."""

class Playback:
    STANDING_HOLD = 30.0
    PLAYLIST = [('standing',STANDING_HOLD),('drinking',None),('standing',STANDING_HOLD),('reading',None)]

    def __init__(self,durations):
        self.durations=dict(durations)
        self.current='standing'
        self.position=0.0
        self.stage_elapsed=0.0
        self.pending=None
        self.automatic=False
        self.playlist_index=0
        self.cycle=0

    @property
    def requested(self):
        return self.pending or self.current

    def request(self,name,automatic=False):
        if name not in self.durations:raise ValueError(name)
        if automatic:
            self.playlist_index=0
            self.stage_elapsed=0.0
        self.automatic=automatic
        # Re-selecting an action preserves its phase and cancels a queued one.
        self.pending=name if name!=self.current else None

    def advance(self,seconds):
        remaining=max(0.0,seconds)
        while remaining>0:
            duration=self.durations[self.current]
            step=min(remaining,duration-self.position)
            self.position+=step
            self.stage_elapsed+=step
            remaining-=step
            if self.position+1e-9<duration:break
            self.position=0.0
            self.cycle+=1
            target=self.pending
            if target is None and self.automatic:
                hold=self.PLAYLIST[self.playlist_index][1]
                if hold is None or self.stage_elapsed+1e-9>=hold:
                    self.playlist_index=(self.playlist_index+1)%len(self.PLAYLIST)
                    target=self.PLAYLIST[self.playlist_index][0]
            if target is not None:
                self.current=target
                self.pending=None
                self.stage_elapsed=0.0
