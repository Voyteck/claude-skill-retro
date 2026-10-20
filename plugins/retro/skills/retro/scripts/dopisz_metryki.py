"""Dopisuje wiersz retro do metryki.csv z metryki.json (wynik sygnaly.py).

Użycie:
  python dopisz_metryki.py --retro R04 --zobowiazania 6 [--metryki PLIK] [--katalog KATALOG_ROBOCZY] [--data RRRR-MM-DD]

--metryki: domyślnie najnowszy `dane/sygnaly-*/metryki.json` w katalogu roboczym. Kolumny, których brakuje
w nagłówku starszego `metryki.csv` (nowe metryki pluginu), są dopisywane na końcu; starsze wiersze mają je puste.
Wiersz z tym samym `retro` jest zastępowany, więc ponowne uruchomienie niczego nie dubluje.
"""
import argparse
import csv
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wspolne  # noqa: E402

NAGLOWEK = pathlib.Path(__file__).resolve().parent.parent / "assets" / "metryki-naglowek.csv"


def kolumny_wzorcowe() -> list:
    return NAGLOWEK.read_text(encoding="utf-8").splitlines()[0].split(",")


def dopisz(plik_csv: pathlib.Path, wiersz: dict) -> dict:
    wzor = kolumny_wzorcowe()
    stare, kolumny = [], []
    if plik_csv.is_file() and plik_csv.read_text(encoding="utf-8").strip():
        with plik_csv.open(encoding="utf-8", newline="") as f:
            czytnik = csv.DictReader(f)
            kolumny = list(czytnik.fieldnames or [])
            stare = list(czytnik)
    dopisane = [k for k in wzor if k not in kolumny]
    kolumny += dopisane
    nieznane = [k for k in wiersz if k not in kolumny]
    wiersz = {k: ("" if v is None else v) for k, v in wiersz.items() if k in kolumny}
    zastapiony = False
    for i, w in enumerate(stare):
        if w.get("retro") == wiersz["retro"]:
            stare[i], zastapiony = wiersz, True
    if not zastapiony:
        stare.append(wiersz)
    with plik_csv.open("w", encoding="utf-8", newline="") as f:
        pisarz = csv.DictWriter(f, fieldnames=kolumny, restval="", extrasaction="ignore", lineterminator="\n")
        pisarz.writeheader()
        pisarz.writerows(stare)
    return {"plik": str(plik_csv), "wiersz": "zastąpiony" if zastapiony else "dopisany",
            "dopisane_kolumny": dopisane, "pominiete_klucze": nieznane}


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--retro", required=True, help="numer retro, np. R04")
    ap.add_argument("--zobowiazania", required=True, type=int, help="liczba aktywnych zobowiązań po retro")
    ap.add_argument("--metryki", help="metryki.json; domyślnie najnowszy w dane/")
    ap.add_argument("--katalog", help="katalog roboczy retro; domyślnie wykryty")
    ap.add_argument("--data", help="data retro (RRRR-MM-DD); domyślnie dziś")
    a = ap.parse_args(argv)
    katalog = pathlib.Path(a.katalog).expanduser() if a.katalog else wspolne.znajdz_katalog_roboczy()[0]
    if katalog is None:
        sys.exit("Nie znaleziono katalogu roboczego retro (--katalog).")
    if a.metryki:
        plik = pathlib.Path(a.metryki)
    else:
        kandydaci = sorted((katalog / "dane").glob("sygnaly-*/metryki.json"), key=lambda p: p.stat().st_mtime)
        if not kandydaci:
            sys.exit("Brak dane/sygnaly-*/metryki.json: uruchom najpierw sygnaly.py albo podaj --metryki.")
        plik = kandydaci[-1]
    metryki = json.loads(plik.read_text(encoding="utf-8"))
    wiersz = {"retro": a.retro, "data": a.data or dt.date.today().isoformat(), **metryki,
              "zobowiazania_aktywne": a.zobowiazania}
    wynik = dopisz(katalog / "metryki.csv", wiersz)
    wynik["metryki"] = str(plik)
    print(json.dumps(wynik, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
