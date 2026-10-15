"""Deterministic checks for real animation boundaries and voice scheduling."""
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from playback import Playback
from voice_actions import VoiceActions


class VoiceActionTests(unittest.TestCase):
    def setUp(self):
        self.clock = Playback({'standing':2.5,'drinking':16,'reading':14})
        self.actions = VoiceActions(random.Random(42))

    def advance(self, seconds, **options):
        self.clock.advance(seconds)
        return self.actions.advance(seconds,self.clock.current,self.clock.cycle,
                                    position=self.clock.position,**options)

    def test_drinking_waits_for_actual_entry_and_repeats_only_at_cycle_start(self):
        self.assertIsNone(self.advance(.5))
        self.clock.request('drinking')
        self.assertIsNone(self.advance(1.5))
        self.assertIsNone(self.advance(.5))
        self.assertIsNone(self.advance(.499))
        self.assertEqual(self.advance(.001),'闲聊·喝酒')
        self.clock.request('drinking')
        self.assertIsNone(self.advance(15))
        self.assertIsNone(self.advance(.5))
        self.assertEqual(self.advance(.5),'闲聊·喝酒')
        self.clock.request('reading')
        self.assertIsNone(self.advance(16))

    def test_manual_voice_is_not_interrupted_or_replayed_late(self):
        self.clock.request('drinking')
        self.assertIsNone(self.advance(2.5,busy=True))
        self.assertIsNone(self.advance(1,busy=False))
        self.assertIsNone(self.advance(15))
        self.assertEqual(self.advance(.5),'闲聊·喝酒')

    def test_delay_uses_media_phase_when_a_frame_crosses_the_entry_boundary(self):
        self.clock.request('drinking')
        self.assertIsNone(self.advance(2.8))
        self.assertIsNone(self.advance(.199))
        self.assertEqual(self.advance(.001),'闲聊·喝酒')

    def test_pausing_keeps_delay_and_stop_or_manual_playback_cancels_pending_line(self):
        self.clock.request('drinking')
        self.assertIsNone(self.advance(2.75))
        self.assertIsNone(self.actions.advance(10,'drinking',self.clock.cycle,
                                               position=self.clock.position,paused=True))
        self.assertEqual(self.advance(.25),'闲聊·喝酒')
        self.assertIsNone(self.advance(15.5))
        self.actions.defer(cancel_drinking=True)
        self.assertIsNone(self.advance(.5))
        self.assertIsNone(self.advance(15.5))
        self.assertIsNone(self.advance(.25,busy=True))
        self.assertIsNone(self.advance(.25,busy=False))

    def test_standing_idle_delays_and_avoids_consecutive_duplicates(self):
        lines, since = [],0
        for _ in range(370):
            since += 1
            line = self.advance(1)
            if line:
                self.assertGreaterEqual(since,45)
                self.assertLessEqual(since,91)
                self.assertIn(line,VoiceActions.IDLE_TITLES)
                if lines:
                    self.assertNotEqual(lines[-1],line)
                lines.append(line)
                since = 0
        self.assertGreaterEqual(len(lines),4)

    def test_pause_mute_busy_and_reading_suppress_idle(self):
        self.advance(.1)
        self.actions.remaining = .1
        for options in ({'enabled':False},{'busy':True},{'paused':True}):
            self.assertIsNone(self.advance(1,**options))
            self.assertEqual(self.actions.remaining,.1)
        self.clock.request('reading')
        self.assertIsNone(self.advance(3))
        for _ in range(120):
            self.assertIsNone(self.advance(1))
        self.clock.request('standing')
        self.assertIsNone(self.advance(14))
        self.assertGreater(self.actions.remaining,43)

    def test_disabled_drinking_cycle_does_not_play_on_unmute(self):
        self.clock.request('drinking')
        self.assertIsNone(self.advance(2.5,enabled=False))
        self.assertIsNone(self.advance(1))
        self.assertIsNone(self.advance(15))
        self.assertEqual(self.advance(.5),'闲聊·喝酒')

    def test_sleep_does_not_cause_idle_catchup_burst(self):
        self.advance(.1)
        self.assertIsNone(self.advance(3600))
        self.assertGreater(self.actions.remaining,43)


if __name__ == '__main__':
    unittest.main()
