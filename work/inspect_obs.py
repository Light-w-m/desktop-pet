from pathlib import Path
import cv2
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parent
videos = [Path(r'E:\OBS\video\2026-10-14 21-04-10.mp4'), Path(r'E:\OBS\video\2026-10-14 21-04-51.mp4')]
for number, path in enumerate(videos, 1):
    cap = cv2.VideoCapture(str(path))
    sheet = Image.new('RGB', (1280, 1128), '#222222')
    draw = ImageDraw.Draw(sheet)
    for i, second in enumerate([0, 1, 2, 3, 4, 6, 8, 10, 12, 14, 16, 18]):
        cap.set(cv2.CAP_PROP_POS_MSEC, second * 1000)
        ok, bgr = cap.read()
        if not ok:
            continue
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        if second in (0, 8, 14):
            Image.fromarray(rgb).save(root / ('obs%d-%02d.png' % (number, second)))
        tile = Image.fromarray(rgb).resize((640, 360), Image.Resampling.LANCZOS)
        x, y = i % 2 * 640, i // 2 * 188
        # Keep the central character area at useful resolution on the sheet.
        tile = tile.crop((160, 0, 480, 360)).resize((320, 180))
        sheet.paste(tile, (x + 160, y))
        draw.text((x + 10, y + 8), '%s / %.1fs' % (path.name, second), fill='white')
    sheet.save(root / ('obs%d-contact.jpg' % number), quality=92)
    cap.release()
