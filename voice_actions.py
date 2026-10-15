"""Schedule paired drinking speech and occasional standing chatter."""
import random


class VoiceActions:
    IDLE_TITLES = ('闲聊·小说','闲聊·出神')
    DRINK_TITLE = '闲聊·喝酒'

    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.pose = None
        self.cycle = None
        self.remaining = self.delay()
        self.last_idle = None

    def delay(self):
        return self.rng.uniform(45,90)

    def defer(self):
        self.remaining = self.delay()

    def advance(self, seconds, pose, cycle, *, enabled=True, busy=False, paused=False):
        changed = pose != self.pose
        new_cycle = cycle != self.cycle
        self.pose, self.cycle = pose,cycle
        if changed:
            self.defer()
        if not enabled or paused:
            return None
        if pose == 'drinking' and new_cycle:
            # Skip a busy cycle instead of playing its line late or interrupting a click.
            return None if busy else self.DRINK_TITLE
        if pose != 'standing' or busy:
            return None
        self.remaining -= min(max(0,seconds),1.0)
        if self.remaining > 0:
            return None
        self.defer()
        choices = [title for title in self.IDLE_TITLES if title != self.last_idle]
        self.last_idle = self.rng.choice(choices)
        return self.last_idle
