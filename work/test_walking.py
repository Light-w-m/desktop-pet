"""Roaming edge/cancellation invariants and completion-driven speech order."""
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from walking import WalkingMotion, WalkingSpeech


class MotionTests(unittest.TestCase):
    def test_horizontal_bounds_across_negative_monitor_origins_and_delayed_ticks(self):
        rng=random.Random(7)
        for limits in ((-2250,-700),(0,900),(-30,-30),(20,21)):
            walk=WalkingMotion();walk.start(limits[0]+5,-530,limits,1.3,None)
            original=walk.x
            walk.advance(5)
            self.assertEqual(walk.x,original,'Preparation moved before first frame')
            walk.preparing=False
            for _ in range(1000):
                walk.advance(rng.uniform(0,20))
                self.assertTrue(limits[0] <= walk.x <= limits[1])
                self.assertEqual(walk.y,-530)
            walk.stop();x=walk.x
            for _ in range(20):walk.advance(.05)
            self.assertEqual(x,walk.x)
            self.assertFalse(walk.visible)

    def test_exact_edge_reverses_and_restart_sets_new_horizontal_line(self):
        walk=WalkingMotion();walk.start(58,123,(0,116),1,None);walk.preparing=False
        self.assertTrue(walk.advance(1));self.assertEqual(walk.x,0);self.assertEqual(walk.direction,1)
        walk.advance(1);self.assertEqual(walk.x,58)
        walk.advance(1);self.assertEqual(walk.x,116);self.assertEqual(walk.direction,-1)
        walk.stop();walk.advance(1)
        self.assertFalse(walk.visible)
        walk.start(50,400,(0,500),1,None)
        self.assertEqual(walk.y,400)


class SpeechTests(unittest.TestCase):
    def setUp(self):
        self.speech=WalkingSpeech(random.Random(42))
        self.available=set(self.speech.TITLES)

    def advance(self,seconds,current=None,**options):
        return self.speech.advance(seconds,current,self.available,**options)

    def test_delayed_start_full_device_completion_gap_and_four_line_order(self):
        waited=0
        while True:
            title=self.advance(.1);waited+=.1
            if title:break
        self.assertTrue(25 <= waited <= 40.1)
        for i,expected in enumerate(self.speech.TITLES):
            self.assertEqual(title,expected)
            self.speech.started(100+i)
            # Even an unexpectedly long recording plays through to completion.
            for _ in range(600):self.assertIsNone(self.advance(.1,100+i))
            self.assertIsNone(self.advance(.1))
            if i < 3:
                self.assertIsNone(self.advance(.799))
                title=self.advance(.001)
            else:
                self.assertIsNone(self.speech.index)
                self.assertTrue(90 <= self.speech.remaining <= 150)

    def test_manual_voice_stop_mute_and_missing_lines_cancel_remaining_sequence(self):
        for event in ('manual','mute','stop'):
            self.speech.remaining=0
            self.assertEqual(self.advance(0),self.speech.TITLES[0])
            self.speech.started(7)
            if event=='manual':self.advance(.1,8)
            elif event=='mute':self.advance(.1,enabled=False)
            else:self.speech.defer()
            self.assertIsNone(self.speech.index)
            self.assertFalse(self.speech.owns(7))
        self.available.remove(self.speech.TITLES[-1]);self.speech.remaining=0
        self.assertIsNone(self.advance(.1))
        self.assertGreaterEqual(self.speech.remaining,90)

    def test_busy_channel_waits_and_restart_drops_queued_lines(self):
        self.speech.remaining=1
        for _ in range(50):self.assertIsNone(self.advance(1,20))
        self.assertEqual(self.speech.remaining,1)
        self.assertEqual(self.advance(1),self.speech.TITLES[0])
        self.speech.started(1);self.speech.restart()
        self.assertIsNone(self.speech.index)
        self.assertFalse(self.speech.owns(1))
        self.assertGreaterEqual(self.speech.remaining,25)


if __name__=='__main__':unittest.main()
