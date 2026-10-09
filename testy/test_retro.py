"""Testy pluginu retro na sztucznych transkrypcjach. Uruchom z katalogu repo:

    python -m unittest discover -s testy -v

Nie dotykają prawdziwego ~/.claude: każdy test ma własny CLAUDE_CONFIG_DIR w katalogu tymczasowym.
"""
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

SKRYPTY = pathlib.Path(__file__).resolve().parent.parent / "plugins" / "retro" / "skills" / "retro" / "scripts"
sys.path.insert(0, str(SKRYPTY))
import wspolne  # noqa: E402


def ts(delta: dt.timedelta = dt.timedelta(minutes=-1)) -> str:
    return (dt.datetime.now(dt.timezone.utc) + delta).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def transkrypcja(cwd: str, tytul: str) -> list:
    """Sesja z kompletem zdarzeń, które liczy sygnaly.py."""
    pytania = [
        {"question": "P1?", "header": "a", "multiSelect": False,
         "options": [{"label": "Tak (rekomendowane)", "description": ""}, {"label": "Nie", "description": ""}]},
        {"question": "P2?", "header": "b", "multiSelect": False,
         "options": [{"label": "Tak (rekomendowane)", "description": ""}, {"label": "Nie", "description": ""}]},
        {"question": "P3?", "header": "c", "multiSelect": False,
         "options": [{"label": "Tak (rekomendowane)", "description": ""}, {"label": "Nie", "description": ""}]},
        {"question": "P4?", "header": "d", "multiSelect": False,
         "options": [{"label": "Tak (rekomendowane)", "description": ""}, {"label": "Nie", "description": ""}]},
        {"question": "P5?", "header": "e", "multiSelect": False,
         "options": [{"label": "Tak (rekomendowane)", "description": ""}, {"label": "Nie", "description": ""}]},
    ]
    odpowiedz = ('The user answered: "P1?"="Tak (rekomendowane)", "P2?"="Nie", "P3?"="zrób inaczej", '
                 '"P4?"="[User dismissed — do not proceed, wait for next instruction]", "P5?"="[No preference]". '
                 "Read the answers carefully.")
    wspolne_pola = {"cwd": cwd, "sessionId": "x"}
    asystent = lambda tresc: {"type": "assistant", "timestamp": ts(), "message": {"model": "claude-opus-5-5", "content": tresc}, **wspolne_pola}  # noqa: E731
    wynik = lambda tid, tekst, blad=False: {"type": "user", "timestamp": ts(), **wspolne_pola, "message": {"content": [  # noqa: E731
        {"type": "tool_result", "tool_use_id": tid, "content": tekst, "is_error": blad}]}}
    return [
        {"type": "custom-title", "customTitle": tytul},
        {"type": "user", "timestamp": ts(dt.timedelta(days=-10)), "origin": {"kind": "human"},
         "message": {"content": "stara wiadomość poza oknem"}, **wspolne_pola},
        {"type": "user", "timestamp": ts(), "origin": {"kind": "human"},
         "message": {"content": "dlaczego znowu to samo?"}, **wspolne_pola},
        asystent([{"type": "text", "text": "Pytam."},
                  {"type": "tool_use", "id": "t1", "name": "AskUserQuestion", "input": {"questions": pytania}}]),
        wynik("t1", odpowiedz),
        asystent([{"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "git push origin main"}}]),
        wynik("t2", "Permission for this action was denied by the Claude Code auto mode classifier. Reason: x", True),
        asystent([{"type": "tool_use", "id": "t3", "name": "Edit", "input": {"file_path": "a.py"}}]),
        wynik("t3", "<tool_use_error>File has not been read yet. Read it first before writing to it.</tool_use_error>", True),
        asystent([{"type": "tool_use", "id": "t4", "name": "Agent",
                   "input": {"subagent_type": "general-purpose", "model": "opus", "prompt": "p"}}]),
        {"type": "system", "subtype": "compact_boundary", "timestamp": ts(), **wspolne_pola},
        {"type": "user", "timestamp": ts(), "origin": {"kind": "peer"}, "message": {"content": "wiadomość innej sesji"}, **wspolne_pola},
    ]


class Srodowisko(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._tmp.name).resolve()
        self.claude = self.tmp / "claude"
        self.repo = self.tmp / "repo"
        self.inny = self.tmp / "inny"
        self.inny.mkdir()
        (self.repo / "pod").mkdir(parents=True)
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        (self.repo / "CLAUDE.md").write_text("# reguły\n- jedna\n", encoding="utf-8")
        subprocess.run(git + ["-C", str(self.repo), "add", "-A"], check=True)
        subprocess.run(git + ["-C", str(self.repo), "commit", "-q", "-m", "fix: start"], check=True)
        for nazwa, cwd in (("repo", self.repo), ("inny", self.inny)):
            folder = self.claude / "projects" / f"f-{nazwa}"
            folder.mkdir(parents=True)
            linie = [json.dumps(r, ensure_ascii=False) for r in transkrypcja(str(cwd), f"sesja {nazwa}")]
            (folder / f"sesja-{nazwa}.jsonl").write_text("\n".join(linie) + "\n", encoding="utf-8")
        (self.claude / "projects" / "f-repo" / "memory").mkdir()
        (self.claude / "projects" / "f-repo" / "memory" / "feedback-x.md").write_text("x", encoding="utf-8")
        self.env = {k: v for k, v in os.environ.items() if k != "RETRO_KATALOG"}
        self.env["CLAUDE_CONFIG_DIR"] = str(self.claude)
        self.env["PYTHONIOENCODING"] = "utf-8"

    def tearDown(self):
        wspolne.git_glowny_katalog.cache_clear()
        self._tmp.cleanup()

    def uruchom(self, skrypt, *argumenty, cwd=None, wejscie=None):
        r = subprocess.run([sys.executable, str(SKRYPTY / skrypt), *argumenty], cwd=cwd or self.tmp, env=self.env,
                           input=wejscie, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def zaloz_konto(self):
        return json.loads(self.uruchom("zaloz.py", "--tryb", "konto", "--katalog", str(self.tmp / "ws")))


class TestZaloz(Srodowisko):
    def test_konto_idempotentne(self):
        pierwszy = self.zaloz_konto()
        ws = self.tmp / "ws"
        for plik in ("konfiguracja.json", "zobowiazania.md", "metryki.csv", "nauki.md", "README.md", ".gitignore"):
            self.assertTrue((ws / plik).is_file(), plik)
        self.assertTrue((ws / ".git").exists())
        wskaznik = json.loads((self.claude / "retro.json").read_text(encoding="utf-8"))
        self.assertEqual(pathlib.Path(wskaznik["katalog_roboczy"]), ws)
        drugi = self.zaloz_konto()
        self.assertEqual(drugi["utworzone"], [])
        self.assertGreater(len(pierwszy["utworzone"]), 5)

    def test_projekt(self):
        wynik = json.loads(self.uruchom("zaloz.py", "--tryb", "projekt", "--repo", str(self.repo / "pod")))
        self.assertEqual(pathlib.Path(wynik["katalog_roboczy"]), self.repo / ".retro")
        self.assertFalse((self.repo / ".retro" / "nauki.md").exists())
        self.assertFalse((self.claude / "retro.json").exists())

    def test_rozpoznanie(self):
        self.zaloz_konto()
        stan = json.loads(self.uruchom("wspolne.py", str(self.inny)))
        self.assertEqual(stan["tryb"], "konto")
        self.assertEqual(stan["nastepny_numer"], 0)


class TestSygnaly(Srodowisko):
    def test_konto_wszystkie_projekty(self):
        self.zaloz_konto()
        wyjscie = self.tmp / "wyn"
        self.uruchom("sygnaly.py", "--od", dt.date.today().isoformat(), "--bez-gh", "--wyjscie", str(wyjscie))
        m = json.loads((wyjscie / "metryki.json").read_text(encoding="utf-8"))
        self.assertEqual(m["sesje"], 2)
        self.assertEqual(m["projekty"], 2)
        self.assertEqual(m["wiad_wlasciciela"], 2)          # stara wiadomość i wiadomość innej sesji pominięte
        self.assertEqual(m["wiad_mozliwa_korekta"], 2)
        self.assertEqual(m["pytania"], 10)
        for klasa in ("pyt_rekomendowana", "pyt_inna", "pyt_wlasna", "pyt_odlozone", "pyt_bez_wyboru"):
            self.assertEqual(m[klasa], 2, klasa)
        self.assertEqual(m["blokady_klasyfikatora"], 2)
        self.assertEqual(m["bledy_narzedzi"], 2)
        self.assertEqual(m["podagenci"], 2)
        self.assertEqual(m["kompakty"], 2)
        self.assertEqual(m["commity"], 1)
        self.assertEqual(m["pamiec_pliki"], 1)
        self.assertGreaterEqual(m["claude_md_linie"], 2)
        os_czasu = (wyjscie / "repo.md").read_text(encoding="utf-8")
        self.assertIn("**odlozone:**", os_czasu)
        self.assertIn("**wlasna:** zrób inaczej", os_czasu)
        self.assertIn("Blokada klasyfikatora", os_czasu)

    def test_poprawka_nazwy_zachowuje_repo(self):
        self.zaloz_konto()
        plik = self.tmp / "ws" / "konfiguracja.json"
        konf = json.loads(plik.read_text(encoding="utf-8"))
        konf["nazwy_projektow"] = [[self.repo.name, "moj-projekt"]]
        plik.write_text(json.dumps(konf), encoding="utf-8")
        wyjscie = self.tmp / "wyn"
        self.uruchom("sygnaly.py", "--od", dt.date.today().isoformat(), "--bez-gh", "--wyjscie", str(wyjscie))
        m = json.loads((wyjscie / "metryki.json").read_text(encoding="utf-8"))
        self.assertTrue((wyjscie / "moj-projekt.md").is_file())
        self.assertEqual(m["commity"], 1)                   # repo znalezione mimo poprawki nazwy
        self.assertIn("| moj-projekt |", (wyjscie / "podsumowanie.md").read_text(encoding="utf-8"))

    def test_projekt_tylko_swoje_sesje(self):
        self.uruchom("zaloz.py", "--tryb", "projekt", "--repo", str(self.repo))
        self.uruchom("sygnaly.py", "--od", dt.date.today().isoformat(), "--bez-gh", cwd=self.repo / "pod")
        wyniki = list((self.repo / ".retro" / "dane").glob("sygnaly-*/metryki.json"))
        self.assertEqual(len(wyniki), 1)
        m = json.loads(wyniki[0].read_text(encoding="utf-8"))
        self.assertEqual(m["sesje"], 1)
        self.assertEqual(m["projekty"], 1)

    def test_bez_katalogu_roboczego_blad(self):
        r = subprocess.run([sys.executable, str(SKRYPTY / "sygnaly.py"), "--od", "2026-01-01"], cwd=self.inny,
                           env=self.env, capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("zaloz.py", r.stderr)


class TestPrzypomnienie(Srodowisko):
    def hook(self, cwd, dzis=None):
        argumenty = ["--dzis", dzis] if dzis else []
        out = self.uruchom("przypomnienie.py", *argumenty, wejscie=json.dumps({"cwd": str(cwd)}))
        return json.loads(out) if out.strip() else None

    def test_milczy_bez_retro(self):
        self.assertIsNone(self.hook(self.inny))

    def test_brak_retro_raz_dziennie_kontekst(self):
        self.zaloz_konto()
        pierwszy = self.hook(self.inny)
        self.assertIn("systemMessage", pierwszy)
        self.assertIn("hookSpecificOutput", pierwszy)
        drugi = self.hook(self.inny)
        self.assertIn("systemMessage", drugi)
        self.assertNotIn("hookSpecificOutput", drugi)

    def test_prog_dni_roboczych(self):
        self.zaloz_konto()
        (self.tmp / "ws" / "retro" / "R00-2026-10-08.md").write_text("# R00\n\n**Status:** zakończone\n", encoding="utf-8")
        self.assertIsNone(self.hook(self.inny, "2026-10-14"))          # 4 dni robocze
        self.assertIsNotNone(self.hook(self.inny, "2026-10-15"))       # 5 dni roboczych

    def test_szkic_nie_resetuje(self):
        self.zaloz_konto()
        (self.tmp / "ws" / "retro" / "R00-2026-10-14.md").write_text("# R00\n\n**Status:** szkic\n", encoding="utf-8")
        self.assertIsNotNone(self.hook(self.inny, "2026-10-15"))

    def test_w_katalogu_roboczym_bez_kontekstu(self):
        self.zaloz_konto()
        wynik = self.hook(self.tmp / "ws")
        self.assertIn("systemMessage", wynik)
        self.assertNotIn("hookSpecificOutput", wynik)

    def test_tryb_projektu(self):
        self.uruchom("zaloz.py", "--tryb", "projekt", "--repo", str(self.repo))
        self.assertIn("w tym projekcie", self.hook(self.repo / "pod")["systemMessage"])
        self.assertIsNone(self.hook(self.inny))


class TestKalendarz(unittest.TestCase):
    def test_swieta(self):
        self.assertEqual(wspolne.wielkanoc(2026), dt.date(2026, 4, 5))
        self.assertEqual(wspolne.wielkanoc(2027), dt.date(2027, 3, 28))
        self.assertFalse(wspolne.dzien_roboczy(dt.date(2026, 11, 11)))
        self.assertFalse(wspolne.dzien_roboczy(dt.date(2026, 12, 24)))
        self.assertTrue(wspolne.dzien_roboczy(dt.date(2026, 11, 11), {"kalendarz": "brak"}))
        self.assertFalse(wspolne.dzien_roboczy(dt.date(2026, 10, 9), {"kalendarz": "PL", "dni_wolne_dodatkowe": ["2026-10-09"]}))
        self.assertEqual(wspolne.dni_robocze_po(dt.date(2026, 10, 8), dt.date(2026, 10, 15)), 5)


if __name__ == "__main__":
    unittest.main()
