"""Wspólne funkcje skillu retro: katalog Claude Code, katalog roboczy, konfiguracja, git, kalendarz.

Tylko biblioteka standardowa; Windows, macOS, Linux.

Katalog roboczy (dokumenty retro, rejestr, metryki, dane) szukany w kolejności:
  1. zmienna środowiskowa RETRO_KATALOG,
  2. tryb projektu: `.retro/konfiguracja.json` w repo bieżącego katalogu (najpierw główny checkout, potem w górę),
  3. tryb konta: wskaźnik `<katalog Claude Code>/retro.json` z polem `katalog_roboczy`.
"""
import datetime as dt
import functools
import json
import os
import pathlib
import re
import shutil
import subprocess

PLIK_KONFIGURACJI = "konfiguracja.json"
KATALOG_PROJEKTU = ".retro"
WSKAZNIK_KONTA = "retro.json"
POLECENIE = "/retro"

DOMYSLNA_KONFIGURACJA = {
    "wersja": 1,
    "tryb": "konto",                       # konto | projekt
    "kalendarz": "PL",                     # PL | brak (sam weekend)
    "dni_wolne_dodatkowe": [],             # ["2026-12-31", ...]
    "prog_przypomnienia_dni_roboczych": 5,
    "rytm_dni_roboczych": 2,
    "ocena_wlasciciela": True,
    "model_podagentow": "opus",
    "godziny_pracy": {"od": "07:30", "do": "17:00", "wieczor_do": "20:00"},
    "nazwy_projektow": [],                 # [["podciąg ścieżki", "nazwa"], ...] — poprawki wykrywania
    "pomin_projekty": [],
    "repozytoria_dodatkowe": {},           # {"nazwa": "ścieżka"} — repo bez sesji w oknie
    "pliki_regul_dodatkowe": [],
    "katalogi_regul_osobno": [],           # ["repo-roots/"] — kopie CLAUDE.md dla innych repo, poza claude_md_linie
    "transkrypcje_dodatkowe": [],          # katalogi `projects` skopiowane z innych maszyn
    "cennik": {},                          # nadpisania references/cennik.json: {"modele": {"claude-x": {...}}}
    "zrodla_zdalne": [],                   # [{"nazwa": "sandbox", "polecenie": [...] | "plik": "..."}] — trend tokenów
    "rejestry_pytan": [],                  # pliki z otwartymi pytaniami do ludzi spoza zespołu
    "gh": None,                            # ścieżka do gh, gdy nie ma go w PATH
}


# ---------------------------------------------------------------- ścieżki

def katalog_claude() -> pathlib.Path:
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return pathlib.Path(env).expanduser() if env else pathlib.Path.home() / ".claude"


@functools.lru_cache(maxsize=512)
def git_glowny_katalog(sciezka: str):
    """Katalog głównego checkoutu repo (także dla worktree) albo None."""
    p = pathlib.Path(sciezka)
    while not p.is_dir():
        if p.parent == p:
            return None
        p = p.parent
    try:
        r = subprocess.run(["git", "-C", str(p), "rev-parse", "--git-common-dir"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0 or not r.stdout.strip():
        return None
    wspolny = pathlib.Path(r.stdout.strip())
    if not wspolny.is_absolute():
        wspolny = (p / wspolny).resolve()
    return str(wspolny.parent if wspolny.name == ".git" else wspolny)


def znajdz_katalog_roboczy(cwd=None):
    """Zwraca (ścieżka, tryb) albo (None, None), gdy retro nie jest założone."""
    env = os.environ.get("RETRO_KATALOG")
    if env:
        return pathlib.Path(env).expanduser(), "env"
    cwd = pathlib.Path(cwd or os.getcwd())
    kandydaci = []
    glowny = git_glowny_katalog(str(cwd))
    if glowny:
        kandydaci.append(pathlib.Path(glowny))
    kandydaci += [cwd, *cwd.parents]
    for k in kandydaci:
        if (k / KATALOG_PROJEKTU / PLIK_KONFIGURACJI).is_file():
            return k / KATALOG_PROJEKTU, "projekt"
    try:
        wskaznik = json.loads((katalog_claude() / WSKAZNIK_KONTA).read_text(encoding="utf-8"))
        k = pathlib.Path(wskaznik["katalog_roboczy"]).expanduser()
        if (k / PLIK_KONFIGURACJI).is_file():
            return k, "konto"
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None, None


def wczytaj_konfiguracje(katalog) -> dict:
    konf = json.loads(json.dumps(DOMYSLNA_KONFIGURACJA))
    if katalog:
        try:
            konf.update(json.loads((pathlib.Path(katalog) / PLIK_KONFIGURACJI).read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    return konf


def sciezka_gh(konf: dict):
    for k in (konf.get("gh"), shutil.which("gh"), r"C:\Program Files\GitHub CLI\gh.exe"):
        if k and os.path.exists(k):
            return k
    return None


# ---------------------------------------------------------------- kalendarz

def wielkanoc(rok: int) -> dt.date:
    """Niedziela Wielkanocna (algorytm Meeusa/Jonesa/Butchera)."""
    a = rok % 19
    b, c = divmod(rok, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    miesiac, dzien = divmod(h + l - 7 * m + 114, 31)
    return dt.date(rok, miesiac, dzien + 1)


@functools.lru_cache(maxsize=64)
def swieta(rok: int, kalendarz: str = "PL") -> frozenset:
    """Ustawowe dni wolne. PL: polskie (Wigilia od 2025); inne wartości: brak świąt."""
    if kalendarz != "PL":
        return frozenset()
    w = wielkanoc(rok)
    dni = {
        dt.date(rok, 1, 1), dt.date(rok, 1, 6),
        w, w + dt.timedelta(days=1),            # Wielkanoc, Poniedziałek Wielkanocny
        dt.date(rok, 5, 1), dt.date(rok, 5, 3),
        w + dt.timedelta(days=49),              # Zielone Świątki (niedziela)
        w + dt.timedelta(days=60),              # Boże Ciało
        dt.date(rok, 8, 15), dt.date(rok, 11, 1), dt.date(rok, 11, 11),
        dt.date(rok, 12, 25), dt.date(rok, 12, 26),
    }
    if rok >= 2025:
        dni.add(dt.date(rok, 12, 24))
    return frozenset(dni)


def dzien_roboczy(d: dt.date, konf: dict = None) -> bool:
    konf = konf or DOMYSLNA_KONFIGURACJA
    if d.weekday() >= 5 or d in swieta(d.year, konf.get("kalendarz", "PL")):
        return False
    return d.isoformat() not in set(konf.get("dni_wolne_dodatkowe") or [])


def dni_robocze_po(od: dt.date, do: dt.date, konf: dict = None) -> int:
    """Liczba dni roboczych d, dla których od < d <= do."""
    n, d = 0, od + dt.timedelta(days=1)
    while d <= do:
        n += dzien_roboczy(d, konf)
        d += dt.timedelta(days=1)
    return n


# ---------------------------------------------------------------- retro

WZOR_PLIKU_RETRO = re.compile(r"^R(\d+)-(\d{4}-\d{2}-\d{2})\.md$")
ZNACZNIK_ZAKONCZONE = re.compile(r"\*\*Status:\*\*\s*zakończone", re.IGNORECASE)


def retro_zakonczone(katalog_retro: pathlib.Path) -> list:
    """Lista (numer, data, ścieżka) zakończonych retro, rosnąco po dacie i numerze."""
    wynik = []
    if not katalog_retro.is_dir():
        return wynik
    for p in katalog_retro.iterdir():
        m = WZOR_PLIKU_RETRO.match(p.name)
        if not m:
            continue
        try:
            naglowek = p.read_text(encoding="utf-8", errors="replace")[:2000]
        except OSError:
            continue
        if ZNACZNIK_ZAKONCZONE.search(naglowek):
            wynik.append((int(m.group(1)), dt.date.fromisoformat(m.group(2)), p))
    return sorted(wynik, key=lambda x: (x[1], x[0]))


def ostatnie_retro(katalog_retro: pathlib.Path):
    lista = retro_zakonczone(katalog_retro)
    return lista[-1] if lista else None


if __name__ == "__main__":
    # Rozpoznanie dla skillu: gdzie jest katalog roboczy dla bieżącego katalogu i jaki ma stan.
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    katalog, tryb = znajdz_katalog_roboczy(sys.argv[1] if len(sys.argv) > 1 else None)
    stan = {"katalog_roboczy": str(katalog) if katalog else None, "tryb": tryb,
            "katalog_claude": str(katalog_claude())}
    if katalog:
        konf = wczytaj_konfiguracje(katalog)
        ostatnie = ostatnie_retro(katalog / "retro")
        numery = [int(m.group(1)) for p in (katalog / "retro").glob("R*.md")
                  if (m := WZOR_PLIKU_RETRO.match(p.name))] if (katalog / "retro").is_dir() else []
        stan.update({
            "konfiguracja": konf,
            "ostatnie_zakonczone": {"numer": ostatnie[0], "data": ostatnie[1].isoformat(), "plik": str(ostatnie[2])}
            if ostatnie else None,
            "nastepny_numer": max(numery, default=-1) + 1,
            "dni_robocze_od_ostatniego": dni_robocze_po(ostatnie[1], dt.date.today(), konf) if ostatnie else None,
        })
    print(json.dumps(stan, ensure_ascii=False, indent=2))
