"""Regression checks for switching during poses and repeated menu choices."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'src'))
from citlali_pet.animation.playback import Playback

class PlaybackTests(unittest.TestCase):
    def setUp(self):
        self.clock=Playback({'standing':2.5,'drinking':16.0,'reading':14.0})

    def test_seated_switch_finishes_return_and_carries_remaining_time(self):
        c=self.clock
        c.request('drinking');c.advance(3)
        c.request('reading');c.advance(10)
        self.assertEqual((c.current,c.position,c.pending),('drinking',10.5,'reading'))
        c.advance(6)
        self.assertEqual((c.current,c.position,c.pending),('reading',.5,None))

    def test_last_selection_wins_without_restarting_the_pose(self):
        c=self.clock
        c.request('drinking');c.advance(5)
        c.request('reading');c.request('standing')
        self.assertEqual(c.position,2.5)
        c.advance(13.5)
        self.assertEqual(c.current,'standing')

    def test_reselecting_current_pose_cancels_pending_without_reset(self):
        c=self.clock
        c.request('reading');c.advance(7)
        c.request('drinking');c.request('reading')
        self.assertIsNone(c.pending)
        self.assertEqual(c.position,4.5)
        c.advance(0)
        self.assertEqual(c.position,4.5)

    def test_automatic_mode_plays_whole_poses_and_standing_intervals(self):
        c=self.clock
        c.request('standing',True);c.advance(30)
        self.assertEqual(c.current,'drinking')
        c.advance(16)
        self.assertEqual(c.current,'standing')
        c.advance(30)
        self.assertEqual(c.current,'reading')
        c.advance(14)
        self.assertEqual(c.current,'standing')

    def test_enabling_automatic_mode_while_lying_waits_for_native_return(self):
        c=self.clock
        c.request('reading');c.advance(4)
        c.request('standing',True);c.advance(1)
        self.assertEqual(c.current,'reading')
        c.advance(11.5)
        self.assertEqual(c.current,'standing')
        self.assertEqual(c.position,0)

    def test_reselecting_automatic_rotation_returns_to_its_standing_stage(self):
        c=self.clock
        c.request('standing',True);c.advance(80)
        self.assertEqual(c.current,'reading')
        c.request('standing',True);c.advance(10)
        self.assertEqual(c.current,'standing')
        c.advance(2.5)
        self.assertEqual(c.current,'standing')

    def test_automatic_standing_outlasts_actions_and_waits_for_native_boundary(self):
        c=Playback({'standing':2.549,'drinking':15.749,'reading':13.599})
        self.assertGreater(c.STANDING_HOLD,max(c.durations['drinking'],c.durations['reading']))
        c.request('standing',True)
        c.advance(30)
        self.assertEqual(c.current,'standing')
        c.advance(.588)
        self.assertEqual(c.current,'drinking')
        self.assertAlmostEqual(c.position,0)
        c.advance(15.749)
        self.assertEqual(c.current,'standing')
        c.advance(30.588)
        self.assertEqual(c.current,'reading')

if __name__=='__main__':unittest.main()
