"""Check lossless reuse, the byte limit and invalidation during resizing."""
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from frame_stream import FrameArchive,PreparedLoopCache


class LoopCacheTests(unittest.TestCase):
    def test_repeat_standing_skips_decode_but_other_actions_still_stream(self):
        archive=FrameArchive.__new__(FrameArchive)
        archive.loop_cache=PreparedLoopCache()
        calls=[]
        frame={'pixels':random.Random(31).randbytes(1024),'offset':(3,7),'size':(16,16)}
        def decode(*key):
            calls.append(key)
            return frame
        archive._read_frame=decode
        self.assertEqual(archive.read('standing',0,(560,480)),frame)
        for _ in range(4):self.assertEqual(archive.read('standing',0,(560,480)),frame)
        self.assertEqual(len(calls),1)
        for _ in range(2):archive.read('drinking',0,(560,480))
        self.assertEqual(len(calls),3)

    def test_budget_stops_admission_without_evicting_the_repeated_prefix(self):
        cache=PreparedLoopCache(32768)
        frame={'pixels':random.Random(81).randbytes(20000),'offset':(1,2),'size':(50,100)}
        cache.remember(0,frame,0)
        cache.remember(1,frame,0)
        self.assertTrue(cache.full)
        self.assertLessEqual(cache.bytes,cache.limit)
        self.assertEqual(cache.lookup(0)[0],frame)
        self.assertIsNone(cache.lookup(1)[0])
        self.assertFalse(cache.lookup(2)[2])

    def test_clear_rejects_old_inflight_resize_and_allows_new_size(self):
        cache=PreparedLoopCache()
        _,old_epoch,_=cache.lookup((0,(560,480)))
        cache.clear()
        frame={'pixels':b'\x10\x20\x30\x40'*100,'offset':(2,3),'size':(10,10)}
        cache.remember((0,(560,480)),frame,old_epoch)
        self.assertEqual(cache.bytes,0)
        _,epoch,_=cache.lookup((0,(728,624)))
        cache.remember((0,(728,624)),frame,epoch)
        self.assertEqual(cache.lookup((0,(728,624)))[0],frame)


if __name__ == '__main__':unittest.main()
