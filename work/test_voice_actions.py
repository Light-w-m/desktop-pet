"""Deterministic checks for real animation boundaries and voice scheduling."""
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'src'))
from citlali_pet.animation.playback import Playback
from citlali_pet.audio.voice_actions import VoiceActions


class VoiceActionTests(unittest.TestCase):
    def setUp(self):
        self.clock = Playback({'standing':2.5,'drinking':16,'reading':14})
        self.actions = VoiceActions(random.Random(42))

    def advance(self, seconds, **options):
        self.clock.advance(seconds)
        options.setdefault('automatic',self.clock.automatic)
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

    def test_automatic_rotation_has_one_idle_line_in_each_long_standing_interval(self):
        self.clock.request('standing',True)
        segments=[]
        segment=None
        busy_until=0
        for step in range(3000):
            now=(step+1)*.1
            title=self.advance(.1,busy=now < busy_until)
            if segment is None or segment['pose'] != self.clock.current:
                segment={'pose':self.clock.current,'start':now,'lines':[]}
                segments.append(segment)
            if title:
                segment['lines'].append((now-segment['start'],title))
                busy_until=now+(9.1 if title == VoiceActions.DRINK_TITLE else 6.6)
        idle=[]
        for segment in segments[:-1]:
            lines=segment['lines']
            if segment['pose'] == 'standing':
                self.assertEqual(len(lines),1)
                elapsed,title=lines[0]
                self.assertTrue(7.9 <= elapsed <= 12.1,lines)
                self.assertIn(title,VoiceActions.IDLE_TITLES)
                idle.append(title)
            elif segment['pose'] == 'drinking':
                self.assertEqual(len(lines),1)
                self.assertEqual(lines[0][1],VoiceActions.DRINK_TITLE)
            else:
                self.assertEqual(lines,[])
        self.assertGreaterEqual(len(idle),6)
        self.assertTrue(all(a != b for a,b in zip(idle,idle[1:])))

    def test_automatic_idle_obeys_pause_mute_manual_priority_and_mode_change(self):
        self.clock.request('standing',True)
        self.advance(.1)
        remaining=self.actions.remaining
        self.assertTrue(7.9 <= remaining <= 12)
        for options in ({'paused':True},{'enabled':False},{'busy':True}):
            self.assertIsNone(self.actions.advance(1,'standing',self.clock.cycle,
                position=self.clock.position,automatic=True,**options))
            self.assertEqual(self.actions.remaining,remaining)
        self.clock.request('standing',False)
        self.advance(.1)
        self.assertTrue(44.9 <= self.actions.remaining <= 90)

    def test_stomp_uses_all_five_lines_without_consecutive_repeats(self):
        available=set(VoiceActions.STOMP_TITLES)
        lines=[self.actions.stomp(available) for _ in range(100)]
        self.assertEqual(set(lines),available)
        self.assertTrue(all(a != b for a,b in zip(lines,lines[1:])))
        self.assertFalse(self.actions.drink_pending)

    def test_stomp_respects_mute_manual_priority_and_deleted_recordings(self):
        available=set(VoiceActions.STOMP_TITLES)
        self.assertIsNone(self.actions.stomp(available,enabled=False))
        self.assertIsNone(self.actions.stomp(available,busy=True))
        self.assertIsNone(self.actions.stomp(set()))
        self.assertIsNone(self.actions.last_stomp)
        one={VoiceActions.STOMP_TITLES[3]}
        self.assertEqual(self.actions.stomp(one),next(iter(one)))
        self.assertEqual(self.actions.stomp(one),next(iter(one)))


if __name__ == '__main__':
    unittest.main()
