from pathlib import Path
import json
import runpy
root=Path(SPECPATH).parent
stage=root/'work'/'repaired-assets'
manifest=json.loads((stage/'manifest.json').read_text(encoding='utf-8'))
pack=json.loads((stage/manifest['playback_pack']).read_text(encoding='utf-8'))
datas=[(str(stage/name),'assets') for name in ['manifest.json',manifest['playback_pack'],pack['data']]]
datas += [(str(path),'assets/expressions') for path in (root/'assets'/'expressions').glob('*.png')]
drag=root/'assets'/'dragging'
assert (drag/'pet-frames.json').is_file(),'Missing prepared dragging animation; extract the matching source-assets package'
datas += [(str(drag/name),'assets/dragging') for name in ('pet-frames.json','pet-frames.bin','source.json')]
assert len(list((root/'assets'/'expressions').glob('*.png')))==9,'Missing expression stickers'
voice_folder=runpy.run_path(str(root/'work'/'prepare_voices.py'))['prepare'](root)
if voice_folder:
    voice_catalog=json.loads((voice_folder/'catalog.json').read_text(encoding='utf-8'))
    datas += [(str(voice_folder/name),'assets/voices') for name in
              ['catalog.json']+[record['file'] for record in voice_catalog['records']]]
a=Analysis([str(root/'desktop_pet.py')],pathex=[],binaries=[],datas=datas,hiddenimports=[],hookspath=[],hooksconfig={},runtime_hooks=[],excludes=['numpy','tkinter','matplotlib','torch'],noarchive=False,optimize=0)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,a.binaries,a.datas,[],name='CitlaliDesktopPet',debug=False,bootloader_ignore_signals=False,strip=False,upx=True,console=False,disable_windowed_traceback=False)
