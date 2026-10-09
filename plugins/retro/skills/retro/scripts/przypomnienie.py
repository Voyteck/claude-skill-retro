"""Hook SessionStart: przypomnienie o retro, gdy od ostatniego minęło >= N dni roboczych.

Szuka katalogu roboczego retro dla katalogu sesji (`cwd` z wejścia hooka). Gdy retro nie jest założone,
milczy. Wypisuje JSON hooka: `systemMessage` (widzi użytkownik) przy każdej nowej sesji oraz
`additionalContext` (widzi Claude) najwyżej raz dziennie i nie w sesji w samym katalogu roboczym.
Nigdy nie kończy się błędem: wyjątek = brak przypomnienia.

Test ręczny:  python przypomnienie.py --dzis 2026-10-15 < wejscie.json
"""
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wspolne  # noqa: E402


def main() -> None:
    try:
        wejscie = json.loads(sys.stdin.read() or "{}")
    except Exception:
        wejscie = {}
    dzis = dt.date.today()
    if "--dzis" in sys.argv:
        dzis = dt.date.fromisoformat(sys.argv[sys.argv.index("--dzis") + 1])

    cwd = wejscie.get("cwd") or None
    katalog, tryb = wspolne.znajdz_katalog_roboczy(cwd)
    if katalog is None:
        return
    konf = wspolne.wczytaj_konfiguracje(katalog)
    prog = int(konf.get("prog_przypomnienia_dni_roboczych", 5))

    ostatnie = wspolne.ostatnie_retro(katalog / "retro")
    if ostatnie:
        numer, data, _ = ostatnie
        zalegle = wspolne.dni_robocze_po(data, dzis, konf)
        opis = f"ostatnie retro R{numer:02d} zakończone {data.isoformat()}, {zalegle} dni roboczych temu"
    else:
        zalegle = 10 ** 6
        opis = "nie ma jeszcze żadnego zakończonego retro"
    if zalegle < prog:
        return

    gdzie = "w tym projekcie" if tryb == "projekt" else f"w sesji w {katalog}"
    wynik = {"systemMessage": f"Retro zaległe: {opis}. Uruchom {wspolne.POLECENIE} ({gdzie})."}

    plik_stempla = katalog / "dane" / "przypomnienie-ostatnie.txt"
    juz_dzis = False
    try:
        juz_dzis = plik_stempla.read_text(encoding="utf-8").strip() == dzis.isoformat()
    except OSError:
        pass
    w_sesji_retro = False
    if cwd:
        try:
            w_sesji_retro = pathlib.Path(cwd).resolve() == katalog.resolve()
        except OSError:
            pass
    if not juz_dzis and not w_sesji_retro:
        wynik["hookSpecificOutput"] = {
            "hookEventName": "SessionStart",
            "additionalContext": (
                f"Przypomnienie o retrospektywie (skill retro): {opis} (próg {prog} dni roboczych). "
                "Nie przerywaj zadania użytkownika. Na końcu pierwszej odpowiedzi w tej sesji zapytaj go "
                "(AskUserQuestion, jeśli jest dostępne), czy robimy retro: „Dziś, w osobnej sesji (rekomendowane)” "
                f"({gdzie}, polecenie {wspolne.POLECENIE}, ok. 20–40 min), „Jutro”, „Pomiń tym razem”. "
                "Samego retro nie uruchamiaj bez jego zgody."
            ),
        }
        try:
            plik_stempla.parent.mkdir(parents=True, exist_ok=True)
            plik_stempla.write_text(dzis.isoformat(), encoding="utf-8")
        except OSError:
            pass
    sys.stdout.write(json.dumps(wynik, ensure_ascii=True))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
