"""Verify package entry points and data locations across source and EXE modes."""
import importlib
import os
from pathlib import Path
import pkgutil
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'src'))
import citlali_pet
from citlali_pet import app,paths


class ProjectLayoutTests(unittest.TestCase):
    def test_all_runtime_modules_import_through_the_package(self):
        modules=[info.name for info in pkgutil.walk_packages(citlali_pet.__path__,citlali_pet.__name__+'.')]
        for name in modules:
            if not name.endswith('.__main__'):importlib.import_module(name)
        self.assertIn('citlali_pet.animation.frame_stream',modules)
        self.assertIn('citlali_pet.audio.voice_output',modules)
        self.assertIn('citlali_pet.ui.pet_menu',modules)
        self.assertEqual({p.name for p in ROOT.glob('*.py')},{'main.py'})

    def test_both_launchers_call_the_same_app_once_from_another_directory(self):
        previous=Path.cwd()
        with tempfile.TemporaryDirectory() as folder,patch.object(app,'main') as main:
            try:
                os.chdir(folder)
                runpy.run_path(str(ROOT/'main.py'),run_name='__main__')
                main.assert_called_once_with()
                main.reset_mock()
                runpy.run_module('citlali_pet',run_name='__main__')
                main.assert_called_once_with()
                self.assertEqual(paths.application_directory(),ROOT)
                self.assertEqual(app.SETTINGS,ROOT/'pet-settings.json')
            finally:os.chdir(previous)

    def test_executable_uses_its_directory_and_embedded_resources(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder).resolve()
            with patch.object(sys,'frozen',True,create=True),patch.object(sys,'executable',str(base/'CitlaliDesktopPet.exe')),patch.object(sys,'_MEIPASS',str(base/'embedded'),create=True):
                values=runpy.run_path(str(ROOT/'src/citlali_pet/paths.py'))
            self.assertEqual(values['APP_DIR'],base)
            self.assertEqual(values['RESOURCE_DIR'],base/'embedded')


if __name__=='__main__':unittest.main()
