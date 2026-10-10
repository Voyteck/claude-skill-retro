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


class TestZamazywanie(unittest.TestCase):
    """Sekrety w testach są zmyślone."""

    def setUp(self):
        import sygnaly
        self.zamaz = sygnaly.zamaz

    def sprawdz(self, tekst, sekret, zostaje=()):
        wynik, n = self.zamaz(tekst)
        self.assertNotIn(sekret, wynik, tekst)
        self.assertGreaterEqual(n, 1)
        for fragment in zostaje:
            self.assertIn(fragment, wynik)

    def test_zamazuje(self):
        self.sprawdz("gh secret set BRAMA_KEY --body 'tajne haslo 1'", "tajne haslo 1", ["gh secret set BRAMA_KEY --body"])
        self.sprawdz('{"command": "gh secret set X --repo a/b --body \\"wartosc z odstepem 9\\""}', "wartosc z odstepem 9")
        self.sprawdz("ustaw API_KEY=abc123def456 w .env", "abc123def456", ["API_KEY="])
        self.sprawdz("hasło: Zimowe7Slonce i dalej", "Zimowe7Slonce", ["hasło:", "i dalej"])
        self.sprawdz("Authorization: Bearer abcdefghij0123456789", "abcdefghij0123456789")
        self.sprawdz("token ghp_" + "a1B2" * 9 + " w logu", "ghp_" + "a1B2" * 9, ["w logu"])
        self.sprawdz("klucz to 9f8e7d6c5b4a39281706f5e4d3c2b1a0 koniec", "9f8e7d6c5b4a39281706f5e4d3c2b1a0", ["koniec"])
        self.sprawdz("-----BEGIN OPENSSH PRIVATE KEY-----\nAAAAB3Nz\n-----END OPENSSH PRIVATE KEY-----", "AAAAB3Nz")

    def test_nie_rusza_dowodow(self):
        teksty = [
            "commit 3f2a9c1d4e5b6a7f8091a2b3c4d5e6f708192a3b jest na main",                      # pełny hash gita
            "obraz php@sha256:" + "0a1b" * 16,                                                   # digest obrazu
            "sesja 6388d886-4e8a-492c-a96c-f0612cd42618 w C:\\Users\\x\\.claude\\projects\\c--Users-x-Workspaces-app",
            "gh pr create --title t --body 'Opis zmiany na 3 zdania'",                             # opis PR to nie sekret
            "klucz: zmiana progu, token wygasa jutro, hasło do ustalenia",                        # proza bez wartości
            "plik feedback_przenoszenie_commitow_bez_checkoutu.md i test_standards_digest_is_one_text.py",
        ]
        for tekst in teksty:
            wynik, n = self.zamaz(tekst)
            self.assertEqual((wynik, n), (tekst, 0), tekst)


class TestSygnalyUzupelnienia(Srodowisko):
    def dopisz(self, nazwa_folderu, plik, rekordy):
        folder = self.claude / "projects" / nazwa_folderu
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / plik).open("a", encoding="utf-8") as f:
            for r in rekordy:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def sygnaly(self):
        self.zaloz_konto()
        wyjscie = self.tmp / "wyn"
        self.uruchom("sygnaly.py", "--od", dt.date.today().isoformat(), "--bez-gh", "--wyjscie", str(wyjscie))
        return wyjscie, json.loads((wyjscie / "metryki.json").read_text(encoding="utf-8"))

    def test_wiadomosc_w_trakcie_pracy(self):
        pola = {"cwd": str(self.repo), "sessionId": "x", "timestamp": ts()}
        kolejka = lambda tekst, rodzaj: {"type": "attachment", **pola, "attachment": {  # noqa: E731
            "type": "queued_command", "commandMode": "prompt", "origin": {"kind": rodzaj}, "prompt": tekst}}
        self.dopisz("f-repo", "sesja-repo.jsonl", [
            kolejka("ale ile to będzie kosztować?", "human"),
            kolejka("<task-notification>koniec</task-notification>", "task-notification"),
            # ta sama treść zapisana także jako zwykła wiadomość: liczy się raz
            {"type": "user", **pola, "origin": {"kind": "human"}, "message": {"content": "ale ile to będzie kosztować?"}},
        ])
        wyjscie, m = self.sygnaly()
        self.assertEqual(m["wiad_wlasciciela"], 3)           # 2 z transkrypcji bazowych + 1 z kolejki
        os_czasu = (wyjscie / "repo.md").read_text(encoding="utf-8")
        self.assertIn("**Właściciel (w trakcie pracy Claude'a):** ale ile to będzie kosztować?", os_czasu)
        self.assertNotIn("task-notification", os_czasu)
        self.assertIn("w trakcie pracy Claude'a: 1", (wyjscie / "podsumowanie.md").read_text(encoding="utf-8"))

    def test_sekret_nie_trafia_do_raportu(self):
        pola = {"cwd": str(self.repo), "sessionId": "x", "timestamp": ts()}
        sekret = "Zm9vYmFyMTIzNDU2Nzg5MGFiY2RlZmdoaWprbG1ub3A"
        self.dopisz("f-repo", "sesja-repo.jsonl", [
            {"type": "user", **pola, "origin": {"kind": "human"},
             "message": {"content": f"powiedz drugiej sesji: klucz bramy to {sekret}"}},
            {"type": "assistant", **pola, "message": {"model": "m", "content": [
                {"type": "tool_use", "id": "s1", "name": "Bash", "input": {"command": f"gh secret set K --body '{sekret}'"}}]}},
            {"type": "user", **pola, "message": {"content": [{"type": "tool_result", "tool_use_id": "s1", "is_error": True,
             "content": "Permission for this action was denied by the Claude Code auto mode classifier. Reason: x"}]}},
        ])
        wyjscie, _ = self.sygnaly()
        for plik in wyjscie.glob("*.md"):
            self.assertNotIn(sekret, plik.read_text(encoding="utf-8"), plik.name)
        os_czasu = (wyjscie / "repo.md").read_text(encoding="utf-8")
        self.assertIn("klucz bramy to [zamazane]", os_czasu)
        self.assertIn("gh secret set K --body [zamazane]", os_czasu)

    def test_sesja_w_scratchpadzie_pominieta(self):
        scratch = self.tmp / "Temp" / "claude" / "C--proj" / "6388d886-4e8a-492c-a96c-f0612cd42618" / "scratchpad"
        scratch.mkdir(parents=True)
        self.dopisz("f-scratchpad", "test.jsonl", transkrypcja(str(scratch), "claude -p"))
        wyjscie, m = self.sygnaly()
        self.assertEqual(m["sesje"], 2)
        self.assertEqual(m["wiad_wlasciciela"], 2)
        self.assertFalse((wyjscie / "scratchpad.md").exists())
        self.assertIn("scratchpadzie (np. testy `claude -p`): 1", (wyjscie / "podsumowanie.md").read_text(encoding="utf-8"))

    def test_reguly_zagniezdzone_i_pamiec_bez_sesji(self):
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-C", str(self.repo)]
        (self.repo / "a" / "b").mkdir(parents=True)
        (self.repo / "a" / "b" / "CLAUDE.md").write_text("# głęboko\n1\n2\n3\n", encoding="utf-8")
        subprocess.run(git + ["add", "a/b/CLAUDE.md"], check=True)
        subprocess.run(git + ["commit", "-q", "-m", "docs: reguły w podkatalogu"], check=True)
        uspiony = self.claude / "projects" / "f-uspiony" / "memory"
        uspiony.mkdir(parents=True)
        (uspiony / "notatka.md").write_text("x", encoding="utf-8")
        wyjscie, m = self.sygnaly()
        podsumowanie = (wyjscie / "podsumowanie.md").read_text(encoding="utf-8")
        self.assertIn(str(pathlib.Path("a") / "b" / "CLAUDE.md"), podsumowanie)
        self.assertEqual(m["claude_md_linie"], 2 + 4)
        self.assertEqual(m["pamiec_pliki"], 2)
        self.assertIn("f-uspiony: 1 plików pamięci", podsumowanie)
        self.assertNotIn("cleanupPeriodDays", podsumowanie)      # okno z dziś mieści się w retencji

    def test_ostrzezenie_o_retencji(self):
        self.zaloz_konto()
        (self.claude / "settings.json").write_text(json.dumps({"cleanupPeriodDays": 10}), encoding="utf-8")
        wyjscie = self.tmp / "wyn"
        od = (dt.date.today() - dt.timedelta(days=11)).isoformat()
        self.uruchom("sygnaly.py", "--od", od, "--bez-gh", "--wyjscie", str(wyjscie))
        self.assertIn("starsze niż 10 dni (`cleanupPeriodDays`)", (wyjscie / "podsumowanie.md").read_text(encoding="utf-8"))


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
