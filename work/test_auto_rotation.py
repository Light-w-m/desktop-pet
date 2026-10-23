"""Exercise the real app's automatic voice dispatch without using speakers."""
import json
import importlib
from pathlib import Path
import random
import sys
from types import SimpleNamespace
import types
import wave

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'src'))
packaged='--packaged' in sys.argv
if packaged:
    from PyInstaller.archive.readers import CArchiveReader
    executable=CArchiveReader(str(ROOT/'work/dist/CitlaliDesktopPet.exe'))
    pyz_name=next(name for name,entry in executable.toc.items() if entry[-1] == 'z')
    embedded=executable.open_embedded_archive(pyz_name)
    for name in ('citlali_pet.animation.playback','citlali_pet.audio.voice_actions','citlali_pet.app'):
        importlib.import_module(name.rpartition('.')[0])
        module=types.ModuleType(name)
        module.__package__=name.rpartition('.')[0]
        module.__file__=str((ROOT/'src'/Path(*name.split('.'))).with_suffix('.py'))
        sys.modules[name]=module
        exec(embedded.extract(name),module.__dict__)
from citlali_pet.app import DesktopPet
from citlali_pet.animation.playback import Playback
from citlali_pet.audio.voice_actions import VoiceActions
from citlali_pet.audio.voice_library import VoiceLibrary

manifest=json.loads((ROOT/'assets/manifest.json').read_text(encoding='utf-8'))
pet=DesktopPet.__new__(DesktopPet)
pet.clock=Playback({name:spec['duration_ms']/1000 for name,spec in manifest['animations'].items()})
pet.clock.request('standing',True)
pet.voice_actions=VoiceActions(random.Random(9))
pet.voices=VoiceLibrary(ROOT,ROOT)
pet.voice_player=SimpleNamespace(current_id=None,muted=False,volume=40)
pet.voice_manual=pet.voice_reaction=pet.paused=False
pet.popup=None
now=busy_until=0.0
segments=[]
events=[]


def play(identifier,*,automatic=False):
    global busy_until
    assert automatic and pet.voice_player.current_id is None,'Automatic line cut an active voice'
    record=pet.voices.get(identifier)
    with wave.open(str(record['path']),'rb') as source:
        seconds=source.getnframes()/source.getframerate()+.25
    busy_until=now+seconds
    pet.voice_player.current_id=identifier
    event={'pose':pet.current,'title':record['title'],'at':round(now,3),
        'stage_seconds':round(pet.clock.stage_elapsed,3),'duration':seconds}
    events.append(event);segments[-1]['events'].append(event)
    return True


pet.play_voice=play
for step in range(3000):
    now=(step+1)*.1
    if now >= busy_until:pet.voice_player.current_id=None
    pet.clock.advance(.1);pet.current=pet.clock.current
    if not segments or segments[-1]['pose'] != pet.current:
        if segments:segments[-1]['duration']=round(now-segments[-1]['start'],3)
        segments.append({'pose':pet.current,'start':now,'events':[]})
    pet.update_automatic_voice(.1)

for segment in segments[:-1]:
    entries=segment['events']
    if segment['pose'] == 'standing':
        assert segment['duration'] >= 30
        assert len(entries) == 1 and entries[0]['title'] in VoiceActions.IDLE_TITLES
        assert 8 <= entries[0]['stage_seconds'] <= 12.1
        assert entries[0]['stage_seconds']+entries[0]['duration'] < segment['duration']
    elif segment['pose'] == 'drinking':
        assert len(entries) == 1 and entries[0]['title'] == VoiceActions.DRINK_TITLE
        assert .5 <= entries[0]['stage_seconds'] <= .61
    else:
        assert entries == []
idle=[entry['title'] for entry in events if entry['pose'] == 'standing']
assert len(idle) >= 6 and all(a != b for a,b in zip(idle,idle[1:]))
report={'simulated_seconds':300,'native_standing_target_seconds':30,
    'packaged_player_and_scheduler_code':packaged,
    'one_random_idle_line_per_automatic_standing_interval':True,
    'idle_lines_finish_before_the_next_action':True,'paired_drinking_voice_preserved':True,
    'actual_desktop_voice_wiring_exercised':True,'audio_not_sent_to_speakers':True,
    'completed_segments':segments[:-1]}
(ROOT/'work/automatic-rotation-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k != 'completed_segments'},indent=2),flush=True)
