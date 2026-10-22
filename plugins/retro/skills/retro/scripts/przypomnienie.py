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
from teksty import t, ustaw  # noqa: E402


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
    ustaw(konf)
    prog = int(konf.get("prog_przypomnienia_dni_roboczych", 5))

    ostatnie = wspolne.ostatnie_retro(katalog / "retro")
    if ostatnie:
        numer, data, _ = ostatnie
        zalegle = wspolne.dni_robocze_po(data, dzis, konf)
        opis = t("przyp_ostatnie", numer=numer, data=data.isoformat(), dni=zalegle)
    else:
        zalegle = 10 ** 6
        opis = t("przyp_zadnego")
    if zalegle < prog:
        return

    gdzie = t("przyp_w_projekcie") if tryb == "projekt" else t("przyp_w_katalogu", katalog=katalog)
    wynik = {"systemMessage": t("przyp_komunikat", opis=opis, polecenie=wspolne.POLECENIE, gdzie=gdzie)}

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
            "additionalContext": t("przyp_kontekst", opis=opis, prog=prog, gdzie=gdzie, polecenie=wspolne.POLECENIE),
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
