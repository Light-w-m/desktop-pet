"""Check every reachable Git revision for files above the 50 MiB project limit."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent


def check(root=ROOT):
    objects = subprocess.check_output(['git','rev-list','--objects','--all'],cwd=root)
    result = subprocess.run(['git','cat-file','--batch-check=%(objectname) %(objecttype) %(objectsize) %(rest)'],
                            input=objects,capture_output=True,cwd=root,check=True)
    blobs = []
    for line in result.stdout.decode('utf-8',errors='replace').splitlines():
        fields = line.split(' ',3)
        if len(fields)>=3 and fields[1]=='blob':
            blobs.append({'bytes':int(fields[2]),'path':fields[3] if len(fields)>3 else fields[0]})
    oversized = [item for item in blobs if item['bytes']>50*1024**2]
    report = {'ready':not oversized,'reachable_blobs':len(blobs),
              'largest_blob':max(blobs,key=lambda item:item['bytes'],default=None),
              'total_blob_mib':sum(item['bytes'] for item in blobs)/1024**2,'oversized':oversized}
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    report = check()
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)
    raise SystemExit(0 if report['ready'] else 1)
