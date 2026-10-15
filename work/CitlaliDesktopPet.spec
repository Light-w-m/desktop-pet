from pathlib import Path
import json
root=Path(SPECPATH).parent
stage=root/'work'/'repaired-assets'
manifest=json.loads((stage/'manifest.json').read_text(encoding='utf-8'))
pack=json.loads((stage/manifest['playback_pack']).read_text(encoding='utf-8'))
datas=[(str(stage/name),'assets') for name in ['manifest.json',manifest['playback_pack'],pack['data']]]
a=Analysis([str(root/'desktop_pet.py')],pathex=[],binaries=[],datas=datas,hiddenimports=[],hookspath=[],hooksconfig={},runtime_hooks=[],excludes=['numpy','tkinter','matplotlib','torch'],noarchive=False,optimize=0)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,a.binaries,a.datas,[],name='CitlaliDesktopPet',debug=False,bootloader_ignore_signals=False,strip=False,upx=True,console=False,disable_windowed_traceback=False)
