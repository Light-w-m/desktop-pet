"""Schedule paired drinking speech and occasional standing chatter."""
import random


class VoiceActions:
    IDLE_TITLES = ('闲聊·小说','闲聊·出神')
    DRINK_TITLE = '闲聊·喝酒'
    DRINK_DELAY = .5
    STOMP_TITLES = ('元素爆发·其一', '元素爆发·其二', '元素爆发·其三',
                    '重受击·其一', '重受击·其二')

    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.pose = None
        self.cycle = None
        self.remaining = self.delay()
        self.last_idle = None
        self.last_stomp = None
        self.drink_pending = False

    def delay(self):
        return self.rng.uniform(45,90)

    def stomp(self, available, *, enabled=True, busy=False):
        """One random line at visible reaction start; skip missing recordings."""
        if not enabled or busy:
            return None
        choices = [title for title in self.STOMP_TITLES if title in available]
        if len(choices) > 1:
            choices = [title for title in choices if title != self.last_stomp]
        if not choices:
            return None
        self.last_stomp = self.rng.choice(choices)
        self.defer(cancel_drinking=True)
        return self.last_stomp

    def defer(self, *, cancel_drinking=False):
        self.remaining = self.delay()
        if cancel_drinking:
            self.drink_pending = False

    def advance(self, seconds, pose, cycle, *, position, enabled=True, busy=False, paused=False):
        changed = pose != self.pose
        new_cycle = cycle != self.cycle
        self.pose, self.cycle = pose,cycle
        if changed or new_cycle:
            self.drink_pending = False
        if changed:
            self.defer()
        if not enabled or busy:
            self.drink_pending = False
            return None
        if paused:
            return None
        if pose == 'drinking':
            if new_cycle:
                self.drink_pending = True
            # Use media position so pausing does not consume the half-second delay.
            if self.drink_pending and position+1e-9 >= self.DRINK_DELAY:
                self.drink_pending = False
                return self.DRINK_TITLE
            return None
        if pose != 'standing':
            return None
        self.remaining -= min(max(0,seconds),1.0)
        if self.remaining > 0:
            return None
        self.defer()
        choices = [title for title in self.IDLE_TITLES if title != self.last_idle]
        self.last_idle = self.rng.choice(choices)
        return self.last_idle
