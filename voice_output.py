"""One PCM clip on a private WinMM handle; never changes device-wide volume."""
import ctypes as C
from ctypes import wintypes as W
import wave


class WaveFormat(C.Structure):
    _pack_ = 2
    _fields_ = [('tag',W.WORD),('channels',W.WORD),('rate',W.DWORD),
                ('bytes_per_second',W.DWORD),('alignment',W.WORD),
                ('bits',W.WORD),('extra',W.WORD)]


class WaveHeader(C.Structure):
    _fields_ = [('data',C.c_void_p),('length',W.DWORD),('recorded',W.DWORD),
                ('user',C.c_size_t),('flags',W.DWORD),('loops',W.DWORD),
                ('next',C.c_void_p),('reserved',C.c_size_t)]


class WaveOutput:
    """Called only by the voice worker. Holds at most the selected clip.

    Handle-scoped volume: https://learn.microsoft.com/en-us/windows/win32/api/mmeapi/nf-mmeapi-waveoutsetvolume
    """
    TAIL_SECONDS = .25

    def __init__(self):
        self.api = C.WinDLL('winmm')
        signatures = {
            'waveOutOpen':(C.POINTER(W.HANDLE),W.UINT,C.POINTER(WaveFormat),C.c_size_t,C.c_size_t,W.DWORD),
            'waveOutPrepareHeader':(W.HANDLE,C.POINTER(WaveHeader),W.UINT),
            'waveOutWrite':(W.HANDLE,C.POINTER(WaveHeader),W.UINT),
            'waveOutReset':(W.HANDLE,),
            'waveOutUnprepareHeader':(W.HANDLE,C.POINTER(WaveHeader),W.UINT),
            'waveOutClose':(W.HANDLE,),
            'waveOutSetVolume':(W.HANDLE,W.DWORD),
        }
        for name, args in signatures.items():
            function = getattr(self.api,name)
            function.argtypes, function.restype = args,W.UINT
        self.handle = W.HANDLE()
        self.header = self.buffer = None
        self.volume = 100

    @staticmethod
    def check(result):
        if result:
            raise RuntimeError(f'Windows audio error {result}')

    @property
    def finished(self):
        return self.header is None or bool(self.header.flags & 1)  # WHDR_DONE

    def set_volume(self, volume):
        self.volume = max(0,min(100,round(volume)))
        if self.handle:
            gain = round(self.volume*65535/100)
            # Pass the opened handle, never a device ID (which changes other apps).
            self.check(self.api.waveOutSetVolume(self.handle,gain | (gain << 16)))

    def stop(self):
        if self.handle:
            # Reset is an abort, not an end-of-stream notification. Once the
            # driver returns the completed buffer, release it without flushing
            # the output path and clipping its last audible samples.
            if self.header is not None and not self.finished:
                self.check(self.api.waveOutReset(self.handle))
            if self.header is not None:
                self.check(self.api.waveOutUnprepareHeader(self.handle,C.byref(self.header),C.sizeof(WaveHeader)))
            self.check(self.api.waveOutClose(self.handle))
        self.handle = W.HANDLE()
        self.header = self.buffer = None

    def __call__(self, path, flags=0):
        self.stop()
        if path is None:
            return
        with wave.open(str(path),'rb') as source:
            channels, rate = source.getnchannels(),source.getframerate()
            if (source.getcomptype() != 'NONE' or source.getsampwidth() != 2
                    or channels not in (1,2) or source.getnframes() > rate*120):
                raise ValueError('Expected a short mono/stereo 16-bit PCM voice')
            frames = source.getnframes()
            pcm = source.readframes(frames)
        if not pcm:
            raise ValueError('Empty voice')
        alignment = channels*2
        if len(pcm) != frames*alignment:
            raise ValueError('Incomplete PCM voice')
        # Leave the original PCM intact. A short silent tail lets the output
        # device/resampler drain before WHDR_DONE makes the clip releasable.
        pcm += bytes(round(rate*self.TAIL_SECONDS)*alignment)
        format = WaveFormat(1,channels,rate,rate*alignment,alignment,16,0)
        self.check(self.api.waveOutOpen(C.byref(self.handle),0xffffffff,C.byref(format),0,0,0))
        try:
            self.set_volume(self.volume)
            self.buffer = C.create_string_buffer(pcm)
            header = WaveHeader(data=C.addressof(self.buffer),length=len(pcm))
            self.check(self.api.waveOutPrepareHeader(self.handle,C.byref(header),C.sizeof(header)))
            self.header = header
            self.check(self.api.waveOutWrite(self.handle,C.byref(header),C.sizeof(header)))
        except Exception:
            self.stop()
            raise
