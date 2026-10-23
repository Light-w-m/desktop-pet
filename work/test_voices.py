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
sys.path.insert(0,str(ROOT/'src'))
from citlali_pet.audio.voice_library import LOCAL_VOICES, VoiceLibrary
from citlali_pet.audio.voices import VoicePlayer
from citlali_pet.audio.voice_output import WaveOutput


def settle(player):
    until = time.perf_counter()+5
    while player.future is not None:
        assert time.perf_counter() < until
        player.poll()
        time.sleep(.002)


def finished(output):
    until = time.perf_counter()+3
    while not output.finished:
        assert time.perf_counter() < until
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
    native = WaveOutput()
    native.set_volume(70)
    native(str(silence))
    assert native.handle and native.buffer is not None
    native.set_volume(30)
    native.api.waveOutGetVolume.argtypes = [C.c_void_p,C.POINTER(C.c_ulong)]
    native.api.waveOutGetVolume.restype = C.c_uint
    actual_volume = C.c_ulong()
    native.check(native.api.waveOutGetVolume(native.handle,C.byref(actual_volume)))
    gain = round(.3*65535)
    assert actual_volume.value == gain | (gain << 16), actual_volume.value
    finished(native)
    assert native.finished
    native.stop()
    assert not native.handle and native.buffer is None
    native_player = VoicePlayer()
    native_player.configure(volume=40)
    for _ in range(8):
        native_player.play(dict(records[0],path=silence))
        settle(native_player)
        native_player.stop()
        settle(native_player)
        assert not native_player.backend.handle and native_player.backend.buffer is None
    native_player.play(dict(records[0],path=silence))
    settle(native_player)
    finished(native_player.backend)
    native_player.poll()
    settle(native_player)
    assert native_player.current_id is None and native_player.backend.buffer is None
    native_player.close()
    class AdjustableBackend:
        def __init__(self):
            self.calls, self.volumes = [],[]
        def __call__(self,path,flags):
            self.calls.append(path)
        def set_volume(self,volume):
            self.volumes.append(volume)
    adjustable = AdjustableBackend()
    player = VoicePlayer(adjustable,volume=70)
    assert player.play(dict(records[0],path=silence))
    settle(player)
    assert adjustable.volumes[-1] == 70
    player.configure(volume=30)
    player.executor.submit(lambda:None).result(timeout=2)
    assert adjustable.volumes[-1] == 30 and player.current_id == 1
    player.configure(muted=True)
    settle(player)
    assert player.muted and player.current_id is None and adjustable.calls[-1] is None
    assert not player.play(dict(records[0],path=silence))
    player.configure(muted=False,volume=0)
    settle(player)
    assert not player.play(dict(records[0],path=silence))
    player.configure(volume=999)
    assert player.volume == 100
    player.configure(volume=-10)
    assert player.volume == 0
    player.close()

sys.argv += ['--qa-seconds','300','--qa-assets',str(ROOT/'work'/'repaired-assets')]
from citlali_pet import app as app
from PIL import Image
from citlali_pet.audio.voices import VoicePicker

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
pet.configure_voice(volume=100,muted=False)
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
    assert selected == expected and len(selected) == len(pet.voices.records)
    click(62)
    ready()
    assert pet.voice_player.current_id is None and played[-1] is None
    volume_before = pet.voice_player.volume
    click(66)
    ready()
    assert pet.voice_player.volume == max(0,volume_before-10)
    click(67)
    ready()
    assert pet.voice_player.volume == volume_before
    # Menus share the double-click-enabled window class: the second press is still a button click.
    left,top,right,bottom = popup.hits[66]
    x,y = round((left+right)/2*popup.dpi),round((top+bottom)/2*popup.dpi)
    for message in (0x0201,0x0202,0x0203,0x0202):
        app.user.SendMessageW(popup.hwnd,message,message != 0x0202,x | (y << 16))
    ready()
    assert pet.voice_player.volume == volume_before-20
    assert pet.expression is None, 'Menu double click triggered a pet reaction'
    pet.configure_voice(volume=volume_before)
    click(65)
    ready()
    assert pet.voice_player.muted
    click(1000+popup.page_records()[0]['id'])
    ready()
    assert pet.voice_player.current_id is None
    click(65)
    ready()
    assert not pet.voice_player.muted
    # Exercise the application wiring without a real speaker or changing its QA clock.
    pet.current = 'drinking'
    pet.clock.cycle += 1
    pet.clock.position = 0
    pet.update_automatic_voice(.02)
    assert pet.voice_player.current_id is None
    pet.clock.position = .499
    pet.update_automatic_voice(.499)
    assert pet.voice_player.current_id is None
    pet.clock.position = .5
    pet.update_automatic_voice(.001)
    settle(pet.voice_player)
    assert pet.voice_player.current_id == 3
    pet.stop_voice()
    settle(pet.voice_player)
    pet.update_automatic_voice(.02)
    assert pet.voice_player.current_id is None
    pet.current = 'standing'
    pet.popup.close()
    pet.update_automatic_voice(.02)
    pet.voice_actions.remaining = 0
    pet.update_automatic_voice(.02)
    settle(pet.voice_player)
    assert pet.voice_player.current_id in (2,4)
    pet.play_voice(1)
    settle(pet.voice_player)
    pet.current = 'drinking'
    pet.clock.cycle += 1
    pet.update_automatic_voice(.02)
    assert pet.voice_player.current_id == 1, 'Automatic voice interrupted manual selection'
    pet.stop_voice()
    settle(pet.voice_player)
    pet.current = pet.clock.current
    # Persistence uses an isolated settings file; preserve unrelated user preferences.
    saved_path, saved_qa = app.SETTINGS,pet.qa_mode
    with tempfile.TemporaryDirectory(prefix='voice-preferences-',dir=ROOT/'work'/'sources') as directory:
        app.SETTINGS = Path(directory)/'pet-settings.json'
        pet.qa_mode = False
        try:
            pet.settings['preserve_test_preference'] = 'kept'
            pet.configure_voice(volume=40,muted=True)
            preferences = json.loads(app.SETTINGS.read_text(encoding='utf-8'))
            assert preferences['voice_volume'] == 40 and preferences['voice_muted']
            assert preferences['preserve_test_preference'] == 'kept'
        finally:
            app.SETTINGS,pet.qa_mode = saved_path,saved_qa
    pet.configure_voice(volume=volume_before,muted=False)
    pet.menu(voices=True)
    popup = pet.popup
    popup.change_page(popup.pages-1)
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
              'private_handle_live_volume_and_buffer_release':True,'mute_zero_volume_and_bounds':True,
              'native_mute_volume_controls':True,'automatic_action_wiring_and_manual_priority':True,
              'rapid_menu_double_clicks_remain_normal_buttons':True,
              'drinking_voice_waits_half_second_of_animation':True,
              'voice_settings_saved_and_other_preferences_preserved':True,
              'gdi_handles_before':before,'gdi_handles_after':after}
    (ROOT/'work'/'voice-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)
finally:
    app.user.DestroyWindow(pet.hwnd)
