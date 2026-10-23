"""Verify namespaced frozen modules, wheel metadata and unchanged media data."""
import hashlib
import json
from pathlib import Path
import zipfile

from PyInstaller.archive.readers import CArchiveReader

ROOT=Path(__file__).resolve().parent.parent
exe=ROOT/'work/dist/CitlaliDesktopPet.exe'
archive=CArchiveReader(str(exe))
pyz=archive.open_embedded_archive(next(name for name,item in archive.toc.items() if item[-1]=='z'))
expected={p.relative_to(ROOT/'src').with_suffix('').as_posix().replace('/','.')
          for p in (ROOT/'src/citlali_pet').rglob('*.py') if p.name not in ('__init__.py','__main__.py')}
assert expected<=set(pyz.toc),expected-set(pyz.toc)
report_path=ROOT/'work/project-layout-validation.json'
report=json.loads(report_path.read_text())
old={Path(p).stem for p in report['runtime_behavior_asts_identical_except_imports_and_app_paths']}
assert not old&set(pyz.toc),'Legacy flat modules remain in the executable'
assert 'main' in archive.toc and 'desktop_pet' not in archive.toc
names={n.replace('\\','/'):n for n in archive.toc}
pack=json.loads(archive.extract(names['assets/pet-frames.json']))
assert hashlib.sha256(archive.extract(names['assets/'+pack['data']])).hexdigest()==report['animation_data_sha256']
wheel=max((ROOT/'work/sources/package-wheel').glob('*.whl'),key=lambda p:p.stat().st_mtime)
with zipfile.ZipFile(wheel) as package:
    for name in expected:assert name.replace('.','/')+'.py' in package.namelist()
    entries=package.read(next(p for p in package.namelist() if p.endswith('.dist-info/entry_points.txt'))).decode()
    assert 'citlali-pet = citlali_pet.app:main' in entries
reports=['walking-package-validation.json','stomp-package-validation.json','standing-package-validation.json',
         'automatic-rotation-validation.json','voice-package-validation.json']
assert all((ROOT/'work'/p).stat().st_mtime>=exe.stat().st_mtime for p in reports)
report.update(frozen_namespaced_modules=sorted(expected),legacy_flat_modules_absent=True,
              wheel_and_gui_entrypoint_verified=True,frozen_behavior_reports=reports)
report_path.write_text(json.dumps(report,indent=2)+'\n')
print('Verified',len(expected),'namespaced frozen modules, Python wheel and pixel-identical embedded media.')
