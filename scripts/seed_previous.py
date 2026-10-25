"""Положить в out/ прошлые выгрузки с прода перед сбором.

Сборщики при сбое источника оставляют прошлый срез ряда с пометкой stale, но на
раннере out/ каждый раз пустой, и разовый сбой Taldau превращался в «потеряны ряды
целиком» и падение деплоя. Торговля не трогается: у неё свой кэш и своя проверка.
"""

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_pages import COPIES, INPUTS, SITE_URL  # noqa: E402

SKIP = {"trade"}


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for key, published in COPIES.items():
        dest = out / INPUTS[key]
        if key in SKIP or dest.exists():
            continue
        url = f"{SITE_URL.rstrip('/')}/macroradar/{published}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "macroradar-seed"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read())
        except Exception as exc:  # без прошлого среза сбор идёт как раньше
            print(f"пропущено {key}: {exc}")
            continue
        dest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        print(f"прошлый срез {key}: {url}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("out"))
