import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRAPER = ROOT / "scraper"
OUT = ROOT / "venex_tmp.json"


def main():
    OUT.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "-m", "scrapy", "crawl", "venex", "-O", str(OUT)],
        cwd=SCRAPER,
        text=True,
    )
    if proc.returncode != 0 or not OUT.exists():
        raise SystemExit(proc.returncode or 1)
    try:
        data = json.loads(OUT.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"JSON Venex inválido: {exc}")
    print(f"VENEX productos generados: {len(data)}")


if __name__ == "__main__":
    main()
