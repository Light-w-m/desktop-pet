"""Download the public source capture; the MP4 stays outside the Git index."""
from pathlib import Path
import json
import subprocess
import urllib.parse

BVID='BV1pUTo6HE8X'
ROOT=Path(__file__).resolve().parent/'sources'
ROOT.mkdir(exist_ok=True)

def request_json(url):
    data=subprocess.check_output(['curl.exe','-sS','--compressed','--max-time','20','-A','Mozilla/5.0','-e','https://www.bilibili.com/','-L',url],creationflags=0x08000000)
    result=json.loads(data)
    if result.get('code')!=0:raise RuntimeError(result.get('message','Source request failed'))
    return result['data']

if __name__=='__main__':
    view=request_json('https://api.bilibili.com/x/web-interface/view?bvid='+BVID)
    params=urllib.parse.urlencode({'bvid':BVID,'cid':view['cid'],'qn':80,'fnval':1})
    playback=request_json('https://api.bilibili.com/x/player/playurl?'+params)
    output=ROOT/'full-idles.mp4'
    subprocess.run(['curl.exe','-sS','--max-time','120','-A','Mozilla/5.0','-e','https://www.bilibili.com/video/'+BVID+'/','-L',playback['durl'][0]['url'],'-o',str(output)],check=True,creationflags=0x08000000)
    print(output)
