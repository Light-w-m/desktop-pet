"""A baked idle endpoint plays fully before its clock continues."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from shake_motion import StompMotion


class StompHandoffTests(unittest.TestCase):
    def test_full_weight_through_last_frame_and_exact_overshoot(self):
        motion=StompMotion();motion.start_once(None,None,1)
        self.assertEqual(motion.advance(10),0)
        self.assertEqual(motion.elapsed,0)
        motion.preparing=False
        motion.advance(.25)
        self.assertEqual(motion.weight,1)
        motion.advance(.74)
        self.assertTrue(motion.active)
        self.assertEqual(motion.weight,1)
        self.assertAlmostEqual(motion.advance(.025),.015)
        self.assertFalse(motion.visible)
        self.assertEqual(motion.elapsed,1)
        self.assertEqual(motion.advance(1),0)

    def test_asset_endpoint_has_no_second_runtime_pose_blend(self):
        motion=StompMotion();motion.start_once(None,None,1);motion.preparing=False
        frame={'pixels':b'\x30\x20\x10\xff','offset':(0,0),'size':(1,1)}
        motion.advance(.99)
        self.assertIs(motion.blend(frame,(1,1)),frame)


if __name__=='__main__':unittest.main()
