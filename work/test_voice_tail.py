"""Verify complete PCM submission, natural draining and immediate explicit stop."""
import ctypes as C
from ctypes import wintypes as W
import json
from pathlib import Path
import struct
import sys
import tempfile
import time
import types
from unittest.mock import patch
import wave

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'src'))
packaged='--packaged' in sys.argv
if packaged:
    from PyInstaller.archive.readers import CArchiveReader
    executable=CArchiveReader(str(ROOT/'work'/'dist'/'CitlaliDesktopPet.exe'))
    pyz_name=next(name for name,entry in executable.toc.items() if entry[-1] == 'z')
    embedded=executable.open_embedded_archive(pyz_name)
    module=types.ModuleType('citlali_pet.audio.voice_output')
    module.__package__='citlali_pet.audio'
    exec(embedded.extract('citlali_pet.audio.voice_output'),module.__dict__)
    sys.modules['citlali_pet.audio.voice_output']=module
from citlali_pet.audio.voice_library import VoiceLibrary
from citlali_pet.audio.voice_output import WaveHeader,WaveOutput
from citlali_pet.audio.voices import VoicePlayer


class FakeFunction:
    def __init__(self,callback):
        self.callback=callback
    def __call__(self,*args):
        return self.callback(*args)


class FakeAPI:
    def __init__(self):
        self.resets=self.closes=0
        self.active=None
        for name in ('waveOutOpen','waveOutPrepareHeader','waveOutWrite','waveOutReset',
                     'waveOutUnprepareHeader','waveOutClose','waveOutSetVolume'):
            setattr(self,name,FakeFunction(getattr(self,'_'+name)))
    def _waveOutOpen(self,handle,*args):
        C.cast(handle,C.POINTER(W.HANDLE)).contents.value=123
        return 0
    def _waveOutPrepareHeader(self,handle,header,size):
        C.cast(header,C.POINTER(WaveHeader)).contents.flags |= 2
        return 0
    def _waveOutWrite(self,handle,header,size):
        self.active=C.cast(header,C.POINTER(WaveHeader)).contents
        self.active.flags |= 16
        return 0
    def _waveOutReset(self,handle):
        self.resets += 1
        self.active.flags=(self.active.flags | 1) & ~16
        return 0
    def _waveOutUnprepareHeader(self,handle,header,size):
        C.cast(header,C.POINTER(WaveHeader)).contents.flags &= ~2
        return 0
    def _waveOutClose(self,handle):
        self.closes += 1
        return 0
    def _waveOutSetVolume(self,*args):
        return 0


library=VoiceLibrary(ROOT,ROOT)
api=FakeAPI()
with patch('citlali_pet.audio.voice_output.C.WinDLL',return_value=api):
    output=WaveOutput()
for record in library.records:
    with wave.open(str(record['path']),'rb') as source:
        pcm=source.readframes(source.getnframes())
        alignment=source.getnchannels()*2
        padding=round(source.getframerate()*output.TAIL_SECONDS)*alignment
    output(record['path'])
    queued=C.string_at(output.header.data,output.header.length)
    assert queued == pcm+bytes(padding), f"PCM was changed or truncated: {record['id']}"
    assert not output.finished
    output.header.flags=(output.header.flags | 1) & ~16
    output.stop()
    assert api.resets == 0, 'Natural completion reset the sound device'
    assert output.header is None and output.buffer is None and not output.handle
assert api.closes == len(library.records)
output(library.records[0]['path'])
output.stop()
assert api.resets == 1, 'Explicit stop failed to abort active playback'

# Check a different sample rate and stereo frame alignment, plus a truncated
# WAV that previously would have played a silently shortened recording.
with tempfile.TemporaryDirectory(prefix='voice-tail-',dir=ROOT/'work'/'sources') as directory:
    path=Path(directory)/'stereo.wav'
    with wave.open(str(path),'wb') as target:
        target.setnchannels(2);target.setsampwidth(2);target.setframerate(22050)
        target.writeframes(struct.pack('<hh',1500,-1500)*1000)
    output(path)
    assert output.header.length == (1000+round(22050*output.TAIL_SECONDS))*4
    output.stop()
    data=path.read_bytes();path.write_bytes(data[:-100])
    try:
        output(path)
        raise AssertionError('Truncated WAV was accepted')
    except ValueError as error:
        assert 'Incomplete' in str(error)


class SilentOutput(WaveOutput):
    def set_volume(self,volume):
        super().set_volume(0)

    @property
    def finished(self):
        done=super().finished
        if done and self.header is not None and self.handle:
            position=C.create_string_buffer(12)
            struct.pack_into('I',position,0,2)
            self.check(self.api.waveOutGetPosition(self.handle,position,12))
            self.last_position=struct.unpack_from('II',position)
        return done


native=SilentOutput()
native.api.waveOutGetPosition.argtypes=[W.HANDLE,C.c_void_p,W.UINT]
native.api.waveOutGetPosition.restype=W.UINT
player=VoicePlayer(native,volume=40)
samples=[]
try:
    with patch.object(native.api,'waveOutReset',wraps=native.api.waveOutReset) as reset:
        for identifier in (51,66,3,29):
            record=library.get(identifier)
            # Deliberately inaccurate metadata must not stop a native clip;
            # completion comes from the queued PCM, including its quiet tail.
            player.play(dict(record,duration_seconds=.01))
            player.future.result(timeout=5)
            started=time.perf_counter()
            expected=native.header.length//(record['channels']*2)
            until=started+record['duration_seconds']+5
            while player.current_id is not None:
                player.poll()
                assert time.perf_counter() < until, 'Native playback did not finish'
                time.sleep(.003)
            kind,played=native.last_position
            assert kind == 2 and played == expected,(identifier,kind,played,expected)
            duration=time.perf_counter()-started
            assert duration >= record['duration_seconds']+native.TAIL_SECONDS-.04
            player.poll()
            while player.future is not None:
                player.poll();time.sleep(.002)
            assert player.current_id is None and native.buffer is None and not native.handle
            assert reset.call_count == 0, 'Natural completion force-reset the real device'
            row={'id':identifier,'source_seconds':record['duration_seconds'],
                'output_seconds':duration,'all_queued_samples_played':played,
                'natural_completion_reset_calls':reset.call_count}
            samples.append(row);print(json.dumps(row),flush=True)
finally:
    player.close()

report={'all_retained_pcm_preserved':len(library.records),'quiet_tail_seconds':WaveOutput.TAIL_SECONDS,
        'embedded_audio_backend':packaged,
        'natural_completion_releases_without_reset':True,'explicit_stop_remains_immediate':True,
        'stereo_and_different_sample_rate':True,'truncated_wav_rejected':True,
        'native_completion_ignores_short_catalog_duration':True,'native_silent_playback':samples}
(ROOT/'work'/'voice-tail-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('Voice tail validation passed.',flush=True)
