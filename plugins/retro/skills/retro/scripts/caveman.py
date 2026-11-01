"""Pliki .md ładowane do kontekstu (reguły, agenci, pamięć, nauki, własne skille i polecenia) w stylu caveman:
lista z oszacowaniem tokenów i stanem kompresji, kopie przed kompresją, kontrola po niej, rejestr i przywracanie.

Kompresję pisze Claude według `references/caveman.md` (bez pluginu caveman); skrypt pilnuje, żeby nic nie zginęło.

Użycie (katalog roboczy: --katalog albo wykryty):
  python caveman.py lista [--wszystkie]           pliki do kompresji (stan z najnowszego `dane/sygnaly-*/pliki-kontekstu.json`)
  python caveman.py kopia --retro R07 PLIK...     kopia w `dane/caveman/R07/` (istniejąca kopia zostaje: to oryginał)
  python caveman.py sprawdz --retro R07 PLIK...   kontrola wobec kopii; bez błędów zapis w `caveman.csv`; kod 1 przy błędach
  python caveman.py przywroc --retro R07 PLIK...  oryginał z kopii, wiersz rejestru usunięty

Pliki samego pluginu retro i zainstalowanych pluginów (`<katalog Claude Code>/plugins/`) nie są kandydatami.
"""
import argparse
import collections
import csv
import datetime as dt
import fnmatch
import hashlib
import json
import pathlib
import re
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wspolne  # noqa: E402
import teksty  # noqa: E402
from teksty import t  # noqa: E402

PLIK_REJESTRU = "caveman.csv"
POLA_REJESTRU = ["retro", "data", "plik", "poziom", "tokeny_przed", "tokeny_po", "sha_po"]
KATALOG_KOPII = pathlib.Path("dane") / "caveman"
PLIK_LISTY = "pliki-kontekstu.json"
POZIOMY = ("wyl", "lekki", "standard", "ultra")
SKILL = pathlib.Path(__file__).resolve().parent.parent
STANY = ("nieskompresowany", "zmieniony", "inny_poziom", "skompresowany")


def tokeny_szac(tekst: str) -> int:
    """Oszacowanie tokenów: znaki / 4 (wystarcza do porównań przed i po)."""
    return round(len(tekst) / 4)


def sha(tekst: str) -> str:
    return hashlib.sha1(tekst.encode("utf-8")).hexdigest()[:12]


def klucz(plik) -> str:
    """Ścieżka jako klucz rejestru: bezwzględna, z `~` dla katalogu domowego, ukośniki POSIX."""
    p = pathlib.Path(plik).expanduser().resolve()
    try:
        return "~/" + p.relative_to(pathlib.Path.home().resolve()).as_posix()
    except ValueError:
        return p.as_posix()


def poziom(konf: dict) -> str:
    p = str(konf.get("caveman") or "standard").strip().lower()
    return p if p in POZIOMY else "standard"


# ---------------------------------------------------------------- kandydaci

def pliki_kontekstu(regul: list, repozytoria: dict, foldery_pamieci: list, katalog_roboczy, konf: dict) -> list:
    """[(rodzaj, projekt, ścieżka)]: reguły (`regul` z `sygnaly.pliki_regul`, bez kopii dla innych repo), agenci,
    pamięć, `nauki.md`, własne skille (`SKILL.md`) i polecenia. Bez plików pluginów i wzorców `caveman_pomin`."""
    claude = wspolne.katalog_claude()
    kandydaci = [("reguly", nazwa, pathlib.Path(p)) for nazwa, p, _, osobno in regul if not osobno]
    bazy = [("~/.claude", claude)] + [(nazwa, pathlib.Path(s) / ".claude") for nazwa, s in repozytoria.items()]
    for nazwa, baza in bazy:
        kandydaci += [("agent", nazwa, p) for p in sorted((baza / "agents").glob("*.md"))]
        kandydaci += [("skill", nazwa, p) for p in sorted((baza / "skills").glob("*/SKILL.md"))]
        kandydaci += [("polecenie", nazwa, p) for p in sorted((baza / "commands").glob("**/*.md"))]
    for folder in foldery_pamieci:
        kandydaci += [("pamiec", folder.name[-40:], p) for p in sorted((pathlib.Path(folder) / "memory").glob("*.md"))]
    if katalog_roboczy is not None and (pathlib.Path(katalog_roboczy) / "nauki.md").is_file():
        kandydaci.append(("nauki", "retro", pathlib.Path(katalog_roboczy) / "nauki.md"))
    pomin = [str(w) for w in konf.get("caveman_pomin") or []]
    wylaczone = [SKILL.resolve(), (claude / "plugins").resolve()]
    wynik, widziane = [], set()
    for rodzaj, projekt, p in kandydaci:
        try:
            r = p.resolve()
            if not r.is_file() or str(r).lower() in widziane:
                continue
        except OSError:
            continue
        if any(r == w or w in r.parents for w in wylaczone):
            continue
        k = klucz(r)
        if any(fnmatch.fnmatch(k, w) or fnmatch.fnmatch(r.name, w) for w in pomin):
            continue
        widziane.add(str(r).lower())
        wynik.append((rodzaj, projekt, r))
    return wynik


def wczytaj_rejestr(katalog) -> list:
    try:
        with (pathlib.Path(katalog) / PLIK_REJESTRU).open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def stan(plik: pathlib.Path, rejestr: list, poz: str):
    """(stan, retro ostatniej kompresji albo None): nieskompresowany | zmieniony (po kompresji) | inny_poziom |
    skompresowany."""
    k = klucz(plik)
    wiersze = [w for w in rejestr if w.get("plik") == k]
    if not wiersze:
        return "nieskompresowany", None
    ost = wiersze[-1]
    try:
        tekst = plik.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "nieskompresowany", None
    if sha(tekst) != ost.get("sha_po"):
        return "zmieniony", ost.get("retro")
    if ost.get("poziom") != poz:
        return "inny_poziom", ost.get("retro")
    return "skompresowany", ost.get("retro")


def opisz(pliki: list, katalog, konf: dict) -> list:
    """[{rodzaj, projekt, plik, tokeny, stan, retro}] dla listy z `pliki_kontekstu`."""
    rejestr = wczytaj_rejestr(katalog) if katalog is not None else []
    poz = poziom(konf)
    wynik = []
    for rodzaj, projekt, p in pliki:
        try:
            tekst = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        s, retro = stan(p, rejestr, poz)
        wynik.append({"rodzaj": rodzaj, "projekt": projekt, "plik": klucz(p), "tokeny": tokeny_szac(tekst),
                      "stan": s, "retro": retro})
    return wynik


def metryki(opisane: list, konf: dict) -> dict:
    """Kolumny `metryki.csv` od 0.6.0."""
    do = [o for o in opisane if o["stan"] != "skompresowany"]
    wyl = poziom(konf) == "wyl"
    return {"pliki_kontekstu": len(opisane), "pliki_kontekstu_tokeny": sum(o["tokeny"] for o in opisane),
            "caveman_do_kompresji": None if wyl else len(do),
            "caveman_do_kompresji_tokeny": None if wyl else sum(o["tokeny"] for o in do)}


def raport(opisane: list, konf: dict, limit: int = 30) -> list:
    poz = poziom(konf)
    l = ["", t("cv_tytul"), ""]
    if not opisane:
        return l + [t("cv_brak_plikow")]
    rodzaje = collections.defaultdict(lambda: [0, 0, 0, 0])
    for o in opisane:
        r = rodzaje[o["rodzaj"]]
        r[0] += 1
        r[1] += o["tokeny"]
        if o["stan"] != "skompresowany":
            r[2] += 1
            r[3] += o["tokeny"]
    l += [t("cv_opis", poziom=poz) if poz != "wyl" else t("cv_wylaczone"), "", t("cv_kolumny_rodzaje"), "|---|---|---|---|---|"]
    for rodzaj, (n, tok, n_do, tok_do) in sorted(rodzaje.items(), key=lambda x: -x[1][1]):
        l.append(f"| {t('cv_rodzaj_' + rodzaj)} | {n} | {tok} | {n_do} | {tok_do} |")
    do = sorted((o for o in opisane if o["stan"] != "skompresowany"), key=lambda o: -o["tokeny"])
    if do and poz != "wyl":
        l += ["", t("cv_kandydaci", n=min(limit, len(do)), wszystkie=len(do)), "", t("cv_kolumny_pliki"), "|---|---|---|---|"]
        l += [f"| `{o['plik']}` | {t('cv_rodzaj_' + o['rodzaj'])} | {o['tokeny']} | "
              f"{t('cv_stan_' + o['stan'], retro=o['retro'] or '—')} |" for o in do[:limit]]
    return l


# ---------------------------------------------------------------- kontrola po kompresji

FENCE = re.compile(r"^(```|~~~)[^\n]*\n.*?^\1[ \t]*$", re.M | re.S)
INLINE = re.compile(r"`[^`\n]+`")
URL = re.compile(r"https?://[^\s)>\]`]+")
NAGLOWEK = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$", re.M)
LICZBA = re.compile(r"(?<![\w.])\d+(?:[.,:]\d+)*")
IDENT = re.compile(r"\b[A-Z]{1,5}-?\d{2,}\b")
KRZYK = re.compile(r"\b[A-ZĄĆĘŁŃÓŚŹŻ]{3,}\b")
SCIEZKA = re.compile(r"(?:~|\.{1,2})?(?:/[\w.@-]+){2,}/?|\b[\w.-]+/[\w./-]*\.[A-Za-z]{1,5}\b")
PRZECZENIA = re.compile(r"\b(?:nie|nigdy|nic\w*|żadn\w*|bez|not|never|no|none|nothing|cannot|without|nor)\b|n't\b", re.I)
ZNACZNIK_LISTY = re.compile(r"^\s*\d+[.)]\s", re.M)
TABELA = re.compile(r"^\s*\|.*\|\s*$")


def _naglowek_yaml(tekst: str):
    linie = tekst.splitlines(keepends=True)
    if not linie or linie[0].strip() != "---":
        return ""
    for i, linia in enumerate(linie[1:], 1):
        if linia.strip() == "---":
            return "".join(linie[:i + 1])
    return ""


def _proza(tekst: str) -> str:
    """Tekst bez nagłówka YAML, bloków kodu i kodu w linii."""
    tekst = tekst[len(_naglowek_yaml(tekst)):]
    return ZNACZNIK_LISTY.sub(" ", INLINE.sub(" ", FENCE.sub(" ", tekst)))


def _tabele(tekst: str) -> list:
    """Liczba wierszy kolejnych tabel (bloki linii `| … |`)."""
    wynik, n = [], 0
    for linia in FENCE.sub("", tekst).splitlines() + [""]:
        if TABELA.match(linia):
            n += 1
        elif n:
            wynik.append(n)
            n = 0
    return wynik


def sprawdz_tekst(oryginal: str, nowy: str) -> dict:
    """{"bledy": [...], "ostrzezenia": [...]}: kompresja nie może zgubić nagłówka YAML, bloków kodu, kodu w linii,
    adresów, nagłówków, wierszy tabel, liczb, identyfikatorów, ścieżek ani słów pisanych wielkimi literami."""
    bledy, ostrz = [], []
    if _naglowek_yaml(oryginal) != _naglowek_yaml(nowy):
        bledy.append(t("cv_b_yaml"))
    if [m.group(0) for m in FENCE.finditer(oryginal)] != [m.group(0) for m in FENCE.finditer(nowy)]:
        bledy.append(t("cv_b_kod"))

    def brak(nazwa, wzor, a, b):
        """Zgubione = dopasowania z `a`, których nie ma w `b` ani nigdzie w nowym tekście (np. przeniesione do kodu)."""
        zgubione = sorted(x for x in set(wzor.findall(a)) - set(wzor.findall(b)) if x not in nowy)
        if zgubione:
            bledy.append(t(nazwa, lista=", ".join(zgubione[:8]) + (" …" if len(zgubione) > 8 else "")))

    bez_kodu_o, bez_kodu_n = FENCE.sub(" ", oryginal), FENCE.sub(" ", nowy)
    brak("cv_b_inline", INLINE, bez_kodu_o, bez_kodu_n)
    brak("cv_b_url", URL, bez_kodu_o, bez_kodu_n)
    proza_o, proza_n = _proza(oryginal), _proza(nowy)
    if NAGLOWEK.findall(FENCE.sub("", oryginal)) != NAGLOWEK.findall(FENCE.sub("", nowy)):
        bledy.append(t("cv_b_naglowki"))
    if _tabele(oryginal) != _tabele(nowy):
        bledy.append(t("cv_b_tabele", przed=_tabele(oryginal), po=_tabele(nowy)))
    brak("cv_b_liczby", LICZBA, proza_o, proza_n)
    brak("cv_b_ident", IDENT, proza_o, proza_n)
    brak("cv_b_sciezki", SCIEZKA, URL.sub(" ", proza_o), URL.sub(" ", proza_n))
    brak("cv_b_krzyk", KRZYK, proza_o, proza_n)
    przed, po = len(PRZECZENIA.findall(proza_o)), len(PRZECZENIA.findall(proza_n))
    if po < przed:
        ostrz.append(t("cv_o_przeczenia", przed=przed, po=po))
    if len(nowy) >= len(oryginal):
        ostrz.append(t("cv_o_dluzszy"))
    return {"bledy": bledy, "ostrzezenia": ostrz}


# ---------------------------------------------------------------- kopie, rejestr, przywracanie

def plik_kopii(katalog: pathlib.Path, retro: str, plik: pathlib.Path) -> pathlib.Path:
    k = klucz(plik)
    nazwa = re.sub(r"[^\w.-]+", "_", k.strip("~/"))[-120:]
    return katalog / KATALOG_KOPII / retro / f"{sha(k)[:6]}-{nazwa}"


def zapisz_rejestr(katalog: pathlib.Path, wiersze: list):
    with (katalog / PLIK_REJESTRU).open("w", encoding="utf-8", newline="") as f:
        pisarz = csv.DictWriter(f, fieldnames=POLA_REJESTRU, extrasaction="ignore", lineterminator="\n")
        pisarz.writeheader()
        pisarz.writerows(wiersze)


def kopia(katalog: pathlib.Path, retro: str, pliki: list) -> list:
    wynik = []
    for p in pliki:
        p = pathlib.Path(p).expanduser().resolve()
        cel = plik_kopii(katalog, retro, p)
        if not p.is_file():
            wynik.append({"plik": klucz(p), "blad": t("cv_brak_pliku")})
            continue
        if cel.exists():
            wynik.append({"plik": klucz(p), "kopia": str(cel), "istniala": True})
            continue
        cel.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, cel)
        wynik.append({"plik": klucz(p), "kopia": str(cel), "tokeny": tokeny_szac(p.read_text(encoding="utf-8",
                                                                                            errors="replace"))})
    return wynik


def sprawdz(katalog: pathlib.Path, retro: str, pliki: list, poz: str, data: str = None) -> list:
    rejestr = wczytaj_rejestr(katalog)
    wynik = []
    for p in pliki:
        p = pathlib.Path(p).expanduser().resolve()
        cel = plik_kopii(katalog, retro, p)
        if not cel.is_file() or not p.is_file():
            wynik.append({"plik": klucz(p), "ok": False, "bledy": [t("cv_brak_kopii", retro=retro)]})
            continue
        orig = cel.read_text(encoding="utf-8", errors="replace")
        nowy = p.read_text(encoding="utf-8", errors="replace")
        w = sprawdz_tekst(orig, nowy)
        przed, po = tokeny_szac(orig), tokeny_szac(nowy)
        rek = {"plik": klucz(p), "ok": not w["bledy"], **w, "tokeny_przed": przed, "tokeny_po": po,
               "oszczednosc_proc": round(100 * (przed - po) / przed, 1) if przed else 0}
        if not w["bledy"]:
            rejestr = [r for r in rejestr if not (r.get("plik") == klucz(p) and r.get("retro") == retro)]
            rejestr.append({"retro": retro, "data": data or dt.date.today().isoformat(), "plik": klucz(p),
                            "poziom": poz, "tokeny_przed": przed, "tokeny_po": po, "sha_po": sha(nowy)})
        wynik.append(rek)
    zapisz_rejestr(katalog, rejestr)
    return wynik


def przywroc(katalog: pathlib.Path, retro: str, pliki: list) -> list:
    rejestr = wczytaj_rejestr(katalog)
    wynik = []
    for p in pliki:
        p = pathlib.Path(p).expanduser().resolve()
        cel = plik_kopii(katalog, retro, p)
        if not cel.is_file():
            wynik.append({"plik": klucz(p), "blad": t("cv_brak_kopii", retro=retro)})
            continue
        shutil.copyfile(cel, p)
        rejestr = [r for r in rejestr if not (r.get("plik") == klucz(p) and r.get("retro") == retro)]
        wynik.append({"plik": klucz(p), "przywrocony": True})
    zapisz_rejestr(katalog, rejestr)
    return wynik


def lista(katalog: pathlib.Path, konf: dict, wszystkie: bool = False) -> dict:
    kandydaci = sorted((katalog / "dane").glob(f"sygnaly-*/{PLIK_LISTY}"), key=lambda p: p.stat().st_mtime)
    if not kandydaci:
        return {"blad": t("cv_brak_listy")}
    dane = json.loads(kandydaci[-1].read_text(encoding="utf-8"))
    pliki = [(d["rodzaj"], d["projekt"], pathlib.Path(d["plik"]).expanduser()) for d in dane]
    opisane = opisz(pliki, katalog, konf)
    if not wszystkie:
        opisane = [o for o in opisane if o["stan"] != "skompresowany"]
    return {"poziom": poziom(konf), "zrodlo": str(kandydaci[-1]), "pliki": sorted(opisane, key=lambda o: -o["tokeny"]),
            "tokeny": sum(o["tokeny"] for o in opisane)}


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("polecenie", choices=["lista", "kopia", "sprawdz", "przywroc"])
    ap.add_argument("pliki", nargs="*")
    ap.add_argument("--retro", help="numer retro, np. R07 (kopia, sprawdz, przywroc)")
    ap.add_argument("--katalog", help="katalog roboczy retro; domyślnie wykryty")
    ap.add_argument("--wszystkie", action="store_true", help="lista: także pliki już skompresowane")
    a = ap.parse_args(argv)
    katalog = pathlib.Path(a.katalog).expanduser() if a.katalog else wspolne.znajdz_katalog_roboczy()[0]
    if katalog is None:
        sys.exit(t("dop_brak_katalogu"))
    konf = wspolne.wczytaj_konfiguracje(katalog)
    teksty.ustaw(konf)
    if a.polecenie == "lista":
        print(json.dumps(lista(katalog, konf, a.wszystkie), ensure_ascii=False, indent=2))
        return 0
    if not a.retro or not a.pliki:
        sys.exit(t("cv_brak_argumentow"))
    if a.polecenie == "kopia":
        wynik = kopia(katalog, a.retro, a.pliki)
    elif a.polecenie == "sprawdz":
        wynik = sprawdz(katalog, a.retro, a.pliki, poziom(konf))
    else:
        wynik = przywroc(katalog, a.retro, a.pliki)
    print(json.dumps(wynik, ensure_ascii=False, indent=2))
    return 1 if any(not w.get("ok", True) or w.get("blad") for w in wynik) else 0


if __name__ == "__main__":
    sys.exit(main())
