"""Launch the desktop pet from a source checkout or a frozen executable."""
from pathlib import Path
import sys

if not getattr(sys, 'frozen', False):
    sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))

from citlali_pet.app import main

if __name__=='__main__':
    main()
