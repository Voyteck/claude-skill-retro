"""Zakłada (albo uzupełnia) katalog roboczy retro. Idempotentny: istniejących plików nie nadpisuje.

Tryb konta (wszystkie projekty z transkrypcji na tym koncie):
  python zaloz.py --tryb konto --katalog ~/retro [opcje]
  → katalog z git init, wskaźnik <katalog Claude Code>/retro.json
Tryb projektu (tylko jedno repo, retro wspólne dla zespołu, commitowane z projektem):
  python zaloz.py --tryb projekt [--repo ŚCIEŻKA]   (domyślnie repo bieżącego katalogu)
  → <repo>/.retro/

Opcje: --kalendarz PL|brak  --prog N  --rytm N  --bez-oceny-wlasciciela  --model-podagentow NAZWA
       --nadpisz-wskaznik (gdy wskaźnik konta prowadzi do innego katalogu)
Wypisuje JSON z listą założonych i pozostawionych plików.
"""
import argparse
import json
import pathlib
import shutil
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wspolne  # noqa: E402

ASSETS = pathlib.Path(__file__).resolve().parent.parent / "assets"


def main(argv=None):
    for strumien in (sys.stdout, sys.stderr):
        try:
            strumien.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tryb", choices=["konto", "projekt"], required=True)
    ap.add_argument("--katalog", help="tryb konta: katalog roboczy (domyślnie ~/retro)")
    ap.add_argument("--repo", help="tryb projektu: repo (domyślnie bieżący katalog)")
    ap.add_argument("--kalendarz", choices=["PL", "brak"], default="PL")
    ap.add_argument("--prog", type=int, default=5, help="dni robocze bez retro do przypomnienia")
    ap.add_argument("--rytm", type=int, default=2, help="zalecany rytm retro w dniach roboczych")
    ap.add_argument("--bez-oceny-wlasciciela", action="store_true")
    ap.add_argument("--model-podagentow", default="opus")
    ap.add_argument("--nadpisz-wskaznik", action="store_true")
    a = ap.parse_args(argv)

    utworzone, pozostawione, uwagi = [], [], []

    if a.tryb == "konto":
        katalog = pathlib.Path(a.katalog or "~/retro").expanduser().resolve()
    else:
        start = pathlib.Path(a.repo or ".").expanduser().resolve()
        glowny = wspolne.git_glowny_katalog(str(start))
        if not glowny:
            sys.exit(f"{start} nie jest w repozytorium git; tryb projektu wymaga repo.")
        katalog = pathlib.Path(glowny) / wspolne.KATALOG_PROJEKTU

    def zapisz(sciezka: pathlib.Path, tresc: str):
        if sciezka.exists():
            pozostawione.append(str(sciezka))
            return
        sciezka.parent.mkdir(parents=True, exist_ok=True)
        sciezka.write_text(tresc, encoding="utf-8")
        utworzone.append(str(sciezka))

    def kopiuj(zrodlo: str, cel: pathlib.Path):
        if cel.exists():
            pozostawione.append(str(cel))
            return
        cel.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ASSETS / zrodlo, cel)
        utworzone.append(str(cel))

    konf = {k: v for k, v in wspolne.DOMYSLNA_KONFIGURACJA.items()}
    konf.update({"tryb": a.tryb, "kalendarz": a.kalendarz, "prog_przypomnienia_dni_roboczych": a.prog,
                 "rytm_dni_roboczych": a.rytm, "ocena_wlasciciela": not a.bez_oceny_wlasciciela,
                 "model_podagentow": a.model_podagentow})
    zapisz(katalog / wspolne.PLIK_KONFIGURACJI, json.dumps(konf, ensure_ascii=False, indent=2) + "\n")
    (katalog / "retro").mkdir(parents=True, exist_ok=True)
    kopiuj("zobowiazania-start.md", katalog / "zobowiazania.md")
    kopiuj("metryki-naglowek.csv", katalog / "metryki.csv")
    kopiuj("readme-katalogu.md", katalog / "README.md")
    zapisz(katalog / ".gitignore", "dane/\n")
    if a.tryb == "konto":
        kopiuj("nauki-start.md", katalog / "nauki.md")
        if not wspolne.git_glowny_katalog(str(katalog)):
            r = subprocess.run(["git", "init", "-q", str(katalog)], capture_output=True, text=True)
            (utworzone if r.returncode == 0 else uwagi).append(
                f"git init {katalog}" if r.returncode == 0 else f"git init nieudany: {r.stderr.strip()}")
        wskaznik = wspolne.katalog_claude() / wspolne.WSKAZNIK_KONTA
        try:
            obecny = json.loads(wskaznik.read_text(encoding="utf-8")).get("katalog_roboczy")
        except (OSError, ValueError):
            obecny = None
        if obecny and pathlib.Path(obecny).expanduser().resolve() != katalog and not a.nadpisz_wskaznik:
            uwagi.append(f"Wskaźnik {wskaznik} prowadzi do {obecny}; nie zmieniono (użyj --nadpisz-wskaznik).")
        elif obecny and pathlib.Path(obecny).expanduser().resolve() == katalog:
            pozostawione.append(str(wskaznik))
        else:
            wskaznik.parent.mkdir(parents=True, exist_ok=True)
            wskaznik.write_text(json.dumps({"katalog_roboczy": str(katalog)}, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
            utworzone.append(str(wskaznik))

    print(json.dumps({"katalog_roboczy": str(katalog), "tryb": a.tryb, "utworzone": utworzone,
                      "pozostawione": pozostawione, "uwagi": uwagi}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
