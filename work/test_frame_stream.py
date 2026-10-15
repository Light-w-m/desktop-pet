"""Check transition prefetch, invalidation and the shared memory bounds."""
from pathlib import Path
import sys
import threading
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from frame_stream import FrameStream


def wait_until(predicate):
    deadline=time.perf_counter()+3
    while not predicate():
        if time.perf_counter() > deadline:
            raise AssertionError('Frame worker did not finish')
        time.sleep(.001)


class Archive:
    animations={name:{'frames':range(80)} for name in ('standing','dragging','stomping')}

    def read(self,name,number,size):
        time.sleep(.003)
        return {'pixels':bytes(4096),'offset':(0,0),'size':(32,32)}


class FrameStreamTests(unittest.TestCase):
    def test_warming_does_not_interrupt_active_plan_and_switch_is_ready(self):
        stream=FrameStream(Archive())
        try:
            stream.get('dragging',0,(32,32))
            plan=stream.plan
            keys=[('stomping',i,(32,32)) for i in range(3)]
            start=time.perf_counter()
            stream.prefetch(keys)
            self.assertLess(time.perf_counter()-start,.02)
            wait_until(lambda:all(stream.peek(*key) is not None for key in keys))
            self.assertEqual(stream.plan,plan)
            self.assertIsNotNone(stream.peek(*plan))
            stream.request(*keys[0])
            self.assertIsNotNone(stream.peek(*keys[0]))
            for index in range(30):
                stream.get('stomping',index,(32,32))
            self.assertLessEqual(stream.peak_cache_frames,12)
            self.assertLessEqual(stream.peak_cache_bytes,24*1024**2)
        finally:
            stream.close()

    def test_clear_rejects_old_inflight_decodes_even_with_the_same_plan(self):
        entered,release=threading.Event(),threading.Event()
        class SlowArchive(Archive):
            version=1
            def read(self,*args):
                version=self.version
                entered.set()
                if version == 1:
                    release.wait(3)
                return {'pixels':bytes([version])*4096,'offset':(0,0),'size':(32,32)}
        archive=SlowArchive()
        stream=FrameStream(archive)
        try:
            key=('standing',0,(32,32))
            stream.request(*key)
            self.assertTrue(entered.wait(2))
            stream.clear()
            archive.version=2
            stream.request(*key)
            release.set()
            wait_until(lambda:stream.peek(*key) is not None)
            self.assertEqual(stream.get(*key)['pixels'][0],2)
            for _ in range(5):
                stream.clear()
                self.assertEqual(stream.get(*key)['pixels'][0],2)
        finally:
            release.set()
            stream.close()

    def test_worker_failure_reaches_waiter_and_nonblocking_peek(self):
        class BrokenArchive(Archive):
            def read(self,*args):
                raise ValueError('Broken frame')
        stream=FrameStream(BrokenArchive())
        try:
            with self.assertRaises(RuntimeError):
                stream.get('standing',0,(32,32))
            with self.assertRaises(RuntimeError):
                stream.peek('standing',0,(32,32))
        finally:
            stream.close()


if __name__ == '__main__':
    unittest.main()
