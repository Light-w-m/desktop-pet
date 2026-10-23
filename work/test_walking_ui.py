"""Exercise native walking interruptions and popup transitions on hidden QA UI."""
import ctypes as C
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'src'))
sys.argv += ['--qa-seconds','300','--qa-assets',str(ROOT/'work/repaired-assets')]
from citlali_pet import app as app
from citlali_pet.ui.menu_view import render_menu
app.user.SetProcessDPIAware()
pet=app.DesktopPet()
app.user.ShowWindow(pet.hwnd,0)
pet.qa_target='standing'
pet.qa_report=ROOT/'work/walk-playback-qa.json'


def pump(seconds):
    end=time.perf_counter()+seconds
    while time.perf_counter()<end:
        pet.tick();time.sleep(.004)


def start():
    assert pet.start_walking()
    pump(.25)
    assert pet.walking.active and not pet.walking.preparing
    return pet.x,pet.y


try:
    checked=[]
    start();x,y=pet.x,pet.y
    pet.walking.left,pet.walking.right=x-12,x+12
    directions=set()
    for _ in range(24):
        pump(.04);directions.add(pet.walking.direction)
        assert pet.y==y
        assert x-12<=pet.x<=x+12
    assert directions=={-1,1}
    for event in ('left_click','double_click','right_click','resize','pause','action'):
        start()
        if event=='left_click':pet.window_proc(pet.hwnd,0x0201,1,0)
        elif event=='double_click':pet.window_proc(pet.hwnd,0x0203,1,0)
        elif event=='right_click':
            # Real popup is nonmodal; hide only this QA window immediately.
            pet.menu();app.user.ShowWindow(pet.popup.hwnd,0);pet.popup.close()
        elif event=='resize':pet.resize(.7)
        elif event=='pause':pet.menu_command(20)
        else:pet.switch('drinking')
        assert not pet.walking.active,event
        position=pet.x,pet.y
        pump(.3)
        assert (pet.x,pet.y)==position,event
        assert not pet.walking.visible,event
        pet.reset_drag();app.user.ReleaseCapture()
        pet.paused=False
        checked.append(event)
    pet.menu_command(14);assert pet.walking.active
    pet.stop_walking();pump(.2)
    state={'auto':False,'requested':'standing','pending':None,'paused':False,'scale':1,'walking':False}
    render_menu(state,dpi=2).save(ROOT/'work/walking-menu-preview.png')
    report={'native_ui':True,'horizontal_line_constant':True,'both_edges_reverse':True,
        'interruptions_stop_and_never_resume':checked,'menu_starts_walking':True}
    (ROOT/'work/walking-ui-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
finally:
    app.user.DestroyWindow(pet.hwnd)
