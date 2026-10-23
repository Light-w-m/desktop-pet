"""Validate restored recordings and the actual reaction voice dispatch silently."""
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import wave

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'src'))
from citlali_pet.app import DesktopPet
from citlali_pet.animation.playback import Playback
from citlali_pet.audio.voice_actions import VoiceActions
from citlali_pet.audio.voice_library import VoiceLibrary
from citlali_pet.audio.voices import VoicePlayer
from citlali_pet.animation.walking import WalkingSpeech
from restore_stomp_voices import RECORDINGS

library=VoiceLibrary(ROOT,ROOT)
selected=[r for r in library.records if r['title'] in VoiceActions.STOMP_TITLES]
assert {r['id'] for r in selected} == set(RECORDINGS)
for record in selected:
    original=library.originals/record['source_file']
    assert hashlib.sha256(original.read_bytes()).hexdigest() == RECORDINGS[record['id']]
    assert hashlib.sha256(record['path'].read_bytes()).hexdigest() == record['sha256']
    with wave.open(str(record['path']),'rb') as source:
        assert source.getsampwidth() == 2 and source.getcomptype() == 'NONE'
        assert source.getframerate() == 48000 and source.getnchannels() == 1
ignored=[str(library.originals/r['source_file']) for r in selected]+[str(r['path']) for r in selected]
result=subprocess.run(['git','check-ignore','--stdin'],input='\n'.join(ignored)+'\n',
                      text=True,capture_output=True,cwd=ROOT,check=True)
assert len(result.stdout.splitlines()) == len(ignored)

calls=[]
pet=DesktopPet.__new__(DesktopPet)
pet.qa_mode=False
pet.voices=library
pet.voice_player=VoicePlayer(lambda path,flags:calls.append(path),volume=40)
pet.voice_actions=VoiceActions(random.Random(42))
pet.walking_speech=WalkingSpeech()
pet.voice_manual=pet.voice_reaction=False
pet.popup=None
pet.paused=False
pet.current='drinking'
pet.clock=Playback({'standing':2.55,'drinking':15.75,'reading':13.6})
pet.clock.current='drinking'
pet.clock.position=.6
try:
    heard=[]
    for _ in range(50):
        pet.play_stomp_voice()
        heard.append(pet.voice_player.current_id)
    assert set(heard) == set(RECORDINGS)
    assert all(a != b for a,b in zip(heard,heard[1:]))
    reaction=pet.voice_player.current_id
    pet.update_automatic_voice(.6)
    assert pet.voice_player.current_id == reaction, 'Drinking replaced the reaction voice'
    pet.voice_player.configure(muted=True)
    pet.play_stomp_voice()
    assert pet.voice_player.current_id is None
    pet.voice_player.configure(muted=False,volume=0)
    pet.play_stomp_voice()
    assert pet.voice_player.current_id is None
    pet.voice_player.configure(volume=40)
    pet.play_voice(51)
    pet.play_stomp_voice()
    assert pet.voice_player.current_id == 51 and pet.voice_manual, 'Reaction interrupted manual playback'
    report={'restored_chinese_recordings':len(selected),'all_original_and_pcm_hashes_valid':True,
        'all_five_randomly_selected_without_consecutive_repeats':True,
        'mute_zero_volume_and_manual_priority':True,'drinking_cannot_interrupt_reaction_voice':True,
        'total_retained_recordings':len(library.records),'audio_files_remain_git_ignored':True}
    (ROOT/'work'/'stomp-voice-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)
finally:
    pet.voice_player.close()
