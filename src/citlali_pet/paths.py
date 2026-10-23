"""Keep source-checkout and standalone EXE data in their original locations."""
from pathlib import Path
import sys

def application_directory():
    if getattr(sys,'frozen',False):
        return Path(sys.executable).resolve().parent
    checkout=Path(__file__).resolve().parents[2]
    if (checkout/'src/citlali_pet').is_dir():
        return checkout
    # An installed wheel uses the directory containing the supplied assets;
    # editable/source launches always resolve the checkout, even from elsewhere.
    return Path.cwd().resolve()


APP_DIR = application_directory()
RESOURCE_DIR = Path(getattr(sys,'_MEIPASS',APP_DIR))
