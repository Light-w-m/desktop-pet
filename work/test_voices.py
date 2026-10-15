"""Check deletion-aware indexes, asynchronous playback and the native voice menu."""
import ctypes as C
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
import wave
import winsound

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from voice_library import LOCAL_VOICES, VoiceLibrary
from voices import VoicePlayer


def settle(player):
    until = time.perf_counter()+5
    while player.future is not None:
        assert time.perf_counter() < until
        player.poll()
        time.sleep(.002)


with tempfile.TemporaryDirectory(prefix='voice-test-',dir=ROOT/'work'/'sources') as directory:
    temporary = Path(directory)
    local = temporary/LOCAL_VOICES
    cache = local/'_playback'
    cache.mkdir(parents=True)
    silence = cache/'001.wav'
    with wave.open(str(silence),'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(48000)
        output.writeframes(bytes(48000*2//10))
    shutil.copy2(silence,cache/'002.wav')
    for name in ('one.ogg','two.ogg'):
        (local/name).write_bytes(b'local test placeholder')
    records = [{'id':i,'title':f'Voice {i}','file':f'{i:03}.wav',
                'source_file':name,'duration_seconds':.1} for i,name in ((1,'one.ogg'),(2,'two.ogg'))]
    (cache/'catalog.json').write_text(json.dumps({'records':records}))
    library = VoiceLibrary(temporary,temporary/'resources')
    assert [r['id'] for r in library.records] == [1,2]
    (local/'two.ogg').unlink()
    assert [r['id'] for r in library.refresh()] == [1], 'Removed audio reappeared'
    calls = []
    def backend(path, flags):
        time.sleep(.025)
        calls.append((path,flags))
    player = VoicePlayer(backend)
    dispatch = []
    for i in range(12):
        started = time.perf_counter()
        player.play(dict(records[i % 2],path=cache/records[i % 2]['file']))
        dispatch.append(time.perf_counter()-started)
    settle(player)
    assert max(dispatch) < .05, 'Audio work blocked the UI caller'
    assert calls[-1][0] == str(cache/'002.wav')
    assert calls[-1][1] & winsound.SND_ASYNC
    time.sleep(.12)
    player.poll()
    assert player.current_id is None
    player.play(dict(records[0],path=silence))
    player.stop()
    settle(player)
    assert player.current_id is None and calls[-1][0] is None
    player.close()
    assert player.closed and calls[-1][0] is None
    # Exercise the real native backend silently with the same PCM format.
    winsound.PlaySound(str(silence),winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    time.sleep(.12)
    winsound.PlaySound(None,0)

sys.argv += ['--qa-seconds','300','--qa-assets',str(ROOT/'work'/'repaired-assets')]
import desktop_pet as app
from PIL import Image
from voices import VoicePicker

app.PinkMenu.activate = False
app.PinkMenu.extra_style = 0x08000000
native_open = app.PinkMenu.open
def hidden_open(self,x,y):
    native_open(self,x,y)
    app.user.ShowWindow(self.hwnd,0)
app.PinkMenu.open = hidden_open
app.user.SetProcessDPIAware()
app.signature(app.user,'SendMessageW',app.LRESULT,app.W.HWND,app.W.UINT,app.WPARAM,app.LPARAM)
app.signature(app.user,'GetGuiResources',app.W.DWORD,app.W.HANDLE,app.W.DWORD)
app.signature(app.kernel,'GetCurrentProcess',app.W.HANDLE)
pet = app.DesktopPet()
pet.qa_report = ROOT/'work'/'voice-playback-qa.json'
app.user.ShowWindow(pet.hwnd,0)
played = []
pet.voice_player.backend = lambda path,flags:played.append(path)


def pump(seconds=.03):
    end = time.perf_counter()+seconds
    message = app.W.MSG()
    while time.perf_counter() < end:
        while app.user.PeekMessageW(C.byref(message),None,0,0,1):
            app.user.TranslateMessage(C.byref(message))
            app.user.DispatchMessageW(C.byref(message))
        pet.tick()
        time.sleep(.002)


def ready():
    end = time.perf_counter()+5
    while pet.popup.paint_future is not None or pet.voice_player.future is not None:
        assert time.perf_counter() < end
        pump(.015)


def click(command):
    popup = pet.popup
    left,top,right,bottom = popup.hits[command]
    x,y = round((left+right)/2*popup.dpi),round((top+bottom)/2*popup.dpi)
    for message in (0x0200,0x0201,0x0202):
        app.user.SendMessageW(popup.hwnd,message,message == 0x0201,x | (y << 16))


try:
    pet.menu()
    assert pet.popup.hits[50][1:4:2] == pet.popup.hits[60][1:4:2]
    assert pet.popup.hits[50][2] < pet.popup.hits[60][0]
    click(60)
    assert isinstance(pet.popup,VoicePicker)
    ready()
    popup = pet.popup
    pixels = C.string_at(popup.bits,popup.width*popup.height*4)
    Image.frombytes('RGBA',(popup.width,popup.height),pixels,'raw','BGRA').save(ROOT/'work'/'voice-picker-native.png')
    elapsed = pet.elapsed
    pump(.25)
    assert pet.elapsed > elapsed+.15, 'Voice picker blocked animation'
    expected = [r['id'] for r in pet.voices.records]
    selected = []
    for page in range(popup.pages):
        assert popup.page == page
        for record in popup.page_records():
            click(1000+record['id'])
            ready()
            assert pet.voice_player.current_id == record['id']
            assert played[-1] == str(record['path'])
            selected.append(record['id'])
        if page+1 < popup.pages:
            click(64)
    assert selected == expected and len(selected) == 29
    click(62)
    ready()
    assert pet.voice_player.current_id is None and played[-1] is None
    app.user.SendMessageW(popup.hwnd,0x0100,37,0)
    assert popup.page == popup.pages-2
    app.user.SendMessageW(popup.hwnd,0x020A,120 << 16,0)
    assert popup.page == popup.pages-3
    click(61)
    assert not isinstance(pet.popup,VoicePicker)
    pet.popup.close()
    process = app.kernel.GetCurrentProcess()
    before = app.user.GetGuiResources(process,0)
    for _ in range(20):
        pet.menu(voices=True)
        ready()
        pet.popup.close()
    after = app.user.GetGuiResources(process,0)
    assert after <= before+1, ('Voice menu leaked GDI handles',before,after)
    report = {'selected_voice_count':len(selected),'all_selected_voices_dispatch':True,
              'deleted_files_filtered':True,'native_pcm_playback_smoke_test':True,
              'latest_request_wins_stop_and_completion':True,'voice_picker_keeps_animation_playing':True,
              'page_mouse_keyboard_wheel':True,'same_row_expression_voice_buttons':True,
              'gdi_handles_before':before,'gdi_handles_after':after}
    (ROOT/'work'/'voice-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)
finally:
    app.user.DestroyWindow(pet.hwnd)
