from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description="Gera o manifesto de atualização do MarketAI")
    p.add_argument("installer",type=Path);p.add_argument("--version",required=True);p.add_argument("--url",required=True);p.add_argument("--mandatory",action="store_true");p.add_argument("--notes",default="Atualização MarketAI")
    a=p.parse_args(); data=a.installer.read_bytes(); sha=hashlib.sha256(data).hexdigest()
    manifest={"available":True,"version":a.version,"channel":"stable","platform":"windows","download_url":a.url,"sha256":sha,"mandatory":a.mandatory,"notes":a.notes}
    out=Path(__file__).resolve().parents[1]/"releases/windows-stable.json";out.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print(out);print("SHA-256:",sha)
if __name__=="__main__":main()
