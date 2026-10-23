"""Prepare local text-chat settings; never install or start a computer agent."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'src'))
from citlali_pet.ui.deepseek import installation_root, save_api_key, settings_path


def prepare(import_key=False):
    root = installation_root()
    for name in ('data','tmp'):
        (root/name).mkdir(parents=True,exist_ok=True)
    if import_key:
        if sys.stdin.isatty():
            raise ValueError('Pass an existing key through stdin, never a command-line argument.')
        save_api_key(sys.stdin.read().strip())
        print('Saved the existing DeepSeek key with Windows account encryption.')
    wrapper = ('@echo off\nchcp 65001 >nul\n'
               f'set "TEMP={root / "tmp"}"\nset "TMP={root / "tmp"}"\n'
               f'set "CITLALI_DEEPSEEK_ROOT={root}"\n'
               f'start "" "{ROOT / "CitlaliDesktopPet.exe"}" --chat\n')
    for name in ('Open Chat.cmd','Open DeepSeek.cmd'):
        (root/name).write_text(wrapper,encoding='utf-8')
    print('Text-chat settings:',settings_path())
    print('No CLI, browser, local agent server or computer tools are used by the pet.')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--import-key-stdin',action='store_true')
    args=parser.parse_args()
    prepare(args.import_key_stdin)
