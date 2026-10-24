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

    def zaloz_konto(self, jezyk="pl"):
        return json.loads(self.uruchom("zaloz.py", "--tryb", "konto", "--katalog", str(self.tmp / "ws"),
                                       "--jezyk", jezyk))


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
        wynik = json.loads(self.uruchom("zaloz.py", "--tryb", "projekt", "--repo", str(self.repo / "pod"), "--jezyk", "pl"))
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
        self.uruchom("zaloz.py", "--tryb", "projekt", "--repo", str(self.repo), "--jezyk", "pl")
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


def wywolanie(mid, delta, model="claude-opus-5-5", wej=0, wyj=0, z5=0, z1h=0, odcz=0, cwd="", **inne):
    """Rekord asystenta z `usage` jak w transkrypcji Claude Code."""
    return {"type": "assistant", "timestamp": ts(delta), "cwd": cwd, "sessionId": "x", **inne, "message": {
        "id": mid, "model": model, "content": [{"type": "text", "text": "ok"}],
        "usage": {"input_tokens": wej, "output_tokens": wyj, "cache_read_input_tokens": odcz,
                  "cache_creation_input_tokens": z5 + z1h,
                  "cache_creation": {"ephemeral_5m_input_tokens": z5, "ephemeral_1h_input_tokens": z1h}}}}


class Test013(Srodowisko):
    """Zmiany 0.1.3: okno od commita retro, [fakt], tokeny, praca bez lokalnych sesji, reguły osobno, CSV."""

    dopisz = TestSygnalyUzupelnienia.dopisz
    sygnaly = TestSygnalyUzupelnienia.sygnaly

    def git(self, katalog, *argumenty, data=None):
        env = dict(os.environ)
        if data:
            env.update(GIT_AUTHOR_DATE=data, GIT_COMMITTER_DATE=data)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-C", str(katalog), *argumenty],
                       check=True, env=env, capture_output=True)

    def konfiguruj(self, **pola):
        plik = self.tmp / "ws" / "konfiguracja.json"
        konf = json.loads(plik.read_text(encoding="utf-8"))
        konf.update(pola)
        plik.write_text(json.dumps(konf), encoding="utf-8")

    def sygnaly_od(self, od, *dodatkowe):
        wyjscie = self.tmp / "wyn"
        self.uruchom("sygnaly.py", "--od", od, "--bez-gh", "--wyjscie", str(wyjscie), *dodatkowe)
        return wyjscie, json.loads((wyjscie / "metryki.json").read_text(encoding="utf-8"))

    def test_okno_od_commita_poprzedniego_retro(self):
        self.zaloz_konto()
        commit = dt.datetime.now().astimezone() - dt.timedelta(minutes=30)
        ws = self.tmp / "ws"
        (ws / "retro" / f"R00-{commit:%Y-%m-%d}.md").write_text("# R00\n\n**Status:** zakończone\n", encoding="utf-8")
        self.git(ws, "add", "retro")
        self.git(ws, "commit", "-q", "-m", "retro(R00)", data=commit.isoformat(timespec="seconds"))
        pola = {"cwd": str(self.repo), "sessionId": "x", "origin": {"kind": "human"}}
        self.dopisz("f-repo", "sesja-repo.jsonl", [
            {"type": "user", "timestamp": ts(dt.timedelta(minutes=-60)), **pola, "message": {"content": "przed commitem retro"}}])
        wyjscie, m = self.sygnaly_od(f"{commit:%Y-%m-%d}")
        self.assertEqual(m["wiad_wlasciciela"], 2)                  # wiadomość sprzed commita retro pominięta
        self.assertEqual(m["okno_od_godzina"], f"{commit:%H:%M}")
        self.assertEqual(m["commity"], 1)                           # commit z setUp jest po commicie retro
        self.assertIn("od commita, który zakończył R00", (wyjscie / "podsumowanie.md").read_text(encoding="utf-8"))
        _, m = self.sygnaly_od(f"{commit:%Y-%m-%d}", "--od-poczatku-dnia")
        self.assertEqual(m["okno_od_godzina"], "00:00")
        _, m = self.sygnaly_od(f"{commit - dt.timedelta(minutes=45):%Y-%m-%dT%H:%M}")
        self.assertEqual(m["wiad_wlasciciela"], 3)                  # godzina podana wprost

    def test_pytanie_o_fakt(self):
        pola = {"cwd": str(self.repo), "sessionId": "x"}
        q = [{"question": "  [fakt] W jakiej sieci jesteś?", "header": "f", "multiSelect": False,
              "options": [{"label": "Dom", "description": ""}, {"label": "Praca", "description": ""}]},
             {"question": "Bez rekomendacji?", "header": "g", "multiSelect": False,
              "options": [{"label": "A", "description": ""}, {"label": "B", "description": ""}]},
             # 0.2.1: „[fakt]” w cytacie w środku decyzji to nie pytanie o fakt
             {"question": "Co zrobić ze skillem retro? Hook pisze „dodaj [fakt]”.", "header": "h", "multiSelect": False,
              "options": [{"label": "Zostaw (rekomendowane)", "description": ""}, {"label": "Zmień", "description": ""}]}]
        self.dopisz("f-repo", "sesja-repo.jsonl", [
            {"type": "assistant", "timestamp": ts(), **pola, "message": {"model": "m", "content": [
                {"type": "tool_use", "id": "f1", "name": "AskUserQuestion", "input": {"questions": q}}]}},
            {"type": "user", "timestamp": ts(), **pola, "message": {"content": [{"type": "tool_result", "tool_use_id": "f1",
             "content": 'The user answered: "  [fakt] W jakiej sieci jesteś?"="hotspot z telefonu", "Bez rekomendacji?"="A", '
                        '"Co zrobić ze skillem retro? Hook pisze „dodaj [fakt]”."="Zmień". Read the answers carefully.'}]}},
        ])
        wyjscie, m = self.sygnaly()
        self.assertEqual(m["pyt_fakt"], 1)
        self.assertEqual(m["pyt_bez_rekomendacji"], 1)
        self.assertEqual(m["pyt_wlasna"], 2)                       # tylko z transkrypcji bazowych
        self.assertEqual(m["pyt_inna"], 3)                         # 2 z transkrypcji bazowych + decyzja z cytatem
        os_czasu = (wyjscie / "repo.md").read_text(encoding="utf-8")
        self.assertIn("**fakt:** hotspot z telefonu", os_czasu)
        self.assertIn("Hook pisze „dodaj [fakt]”. → **inna:** Zmień", os_czasu)

    def test_tokeny_i_koszt(self):
        self.zaloz_konto()
        cwd = str(self.inny)
        h = lambda godz, minuty=0: dt.timedelta(hours=-godz, minutes=-minuty)  # noqa: E731
        czlowiek = lambda delta, tekst: {"type": "user", "timestamp": ts(delta), "cwd": cwd, "sessionId": "x",  # noqa: E731
                                         "origin": {"kind": "human"}, "message": {"content": tekst}}
        self.dopisz("f-tok", "sesja-tok.jsonl", [
            czlowiek(h(3, 1), "start"),
            wywolanie("m1", h(3), wej=10, wyj=1, z1h=40000, cwd=cwd),            # częściowy usage w trakcie strumienia
            wywolanie("m1", h(3), wej=10, wyj=100, z1h=40000, cwd=cwd),          # pełny: $0.32204
            wywolanie("m2", h(2, 59), wyj=200, z5=5000, odcz=40000, cwd=cwd),    # $0.037
            czlowiek(h(1, 1), "wracam"),
            wywolanie("m3", h(1), z1h=250000, cwd=cwd),                          # wybudzenie po ~2 h: $2.00
            wywolanie("syn", h(1), model="<synthetic>", wyj=999, cwd=cwd),       # pomijane
        ])
        self.dopisz("f-tok", "fork.jsonl", [
            wywolanie("m1", h(3), wej=10, wyj=100, z1h=40000, cwd=cwd),          # kopia: liczona raz
            wywolanie("m4", h(0, 30), odcz=100000, cwd=cwd),                     # $0.02
        ])
        pod = self.claude / "projects" / "f-tok" / "sesja-tok" / "subagents"
        pod.mkdir(parents=True)
        (pod / "agent-a1.meta.json").write_text(json.dumps({"agentType": "Explore"}), encoding="utf-8")
        (pod / "agent-a1.jsonl").write_text("\n".join(json.dumps(r) for r in [
            wywolanie("s1", h(2, 50), model="claude-haiku-4-5-20251001", wej=1000, wyj=1000, cwd=cwd),  # $0.006
            wywolanie("s2", h(2, 49), wyj=1000, cwd=cwd),                                               # $0.02
        ]) + "\n", encoding="utf-8")
        wyjscie, m = self.sygnaly_od((dt.date.today() - dt.timedelta(days=1)).isoformat())
        self.assertEqual(m["wywolania_api"], 6)
        self.assertEqual(m["koszt_api_usd"], 2.41)                   # 2.40504
        self.assertEqual(m["wiad_wlasciciela"], 4)
        self.assertEqual(m["koszt_na_wiadomosc_usd"], 0.6)
        self.assertEqual(m["kontekst_mediana"], 72500)               # 40010, 45000, 100000, 250000
        self.assertEqual(m["kontekst_ponad_200k_proc"], 25.0)
        self.assertEqual(m["podagenci_koszt_proc"], 1.1)             # 0.026 / 2.40504
        self.assertEqual(m["podagenci_opus_koszt_proc"], 76.9)       # 0.02 / 0.026
        self.assertEqual(m["wybudzenia"], 1)
        self.assertEqual(m["wybudzenia_koszt_usd"], 2.0)
        self.assertEqual(m["kontekst_startowy_mediana"], 40010)      # fork (z kopią) się nie liczy
        podsumowanie = (wyjscie / "podsumowanie.md").read_text(encoding="utf-8")
        self.assertIn("## Tokeny i koszt", podsumowanie)
        self.assertIn("`sesja-to` po 2.0 h: zapis 250k, $2.00", podsumowanie)
        self.assertIn("$2.39 |", (wyjscie / "inny.md").read_text(encoding="utf-8"))   # koszt sesji z podagentami

    def test_cennik_z_konfiguracji_i_nieznany_model(self):
        self.zaloz_konto()
        cwd = str(self.inny)
        self.dopisz("f-tok", "s.jsonl", [wywolanie("n1", dt.timedelta(minutes=-2), model="claude-nowy-9", wyj=1_000_000, cwd=cwd),
                                         wywolanie("n2", dt.timedelta(minutes=-1), model="claude-inny-1", wyj=10, cwd=cwd)])
        self.konfiguruj(cennik={"modele": {"claude-nowy": {"wejscie": 1, "wyjscie": 3, "zapis_5m": 1, "zapis_1h": 2, "odczyt": 0.1}}})
        wyjscie, m = self.sygnaly_od(dt.date.today().isoformat())
        self.assertEqual(m["koszt_api_usd"], 3.0)
        self.assertIn("`claude-inny-1` (1 wywołań)", (wyjscie / "podsumowanie.md").read_text(encoding="utf-8"))

    def test_commity_bez_lokalnych_sesji(self):
        self.zaloz_konto()
        obcy = self.tmp / "obcy"
        subprocess.run(["git", "init", "-q", str(obcy)], check=True)
        for i in range(3):
            (obcy / f"p{i}.txt").write_text(str(i), encoding="utf-8")
            self.git(obcy, "add", "-A")
            self.git(obcy, "commit", "-q", "-m", f"feat: {i}")
        self.konfiguruj(repozytoria_dodatkowe={"obcy": str(obcy)})
        wyjscie, m = self.sygnaly_od(dt.date.today().isoformat())
        self.assertEqual(m["commity"], 4)
        self.assertEqual(m["commity_bez_sesji"], 3)                  # commit w repo z sesją jest „lokalny”
        self.assertIn("obcy: 3 z 3 commitów", (wyjscie / "podsumowanie.md").read_text(encoding="utf-8"))

    def test_reguly_osobno(self):
        for nazwa in ("a", "b", "c"):
            (self.repo / "repo-roots" / nazwa).mkdir(parents=True)
            (self.repo / "repo-roots" / nazwa / "CLAUDE.md").write_text("1\n2\n3\n", encoding="utf-8")
        self.git(self.repo, "add", "-A")
        self.git(self.repo, "commit", "-q", "-m", "docs: kopie reguł")
        wyjscie, m = self.sygnaly()
        self.assertEqual(m["claude_md_linie"], 2 + 9)
        self.assertIn("`repo-roots/`: 3 plików, 9 linii", (wyjscie / "podsumowanie.md").read_text(encoding="utf-8"))
        self.konfiguruj(katalogi_regul_osobno=["repo-roots"])
        wyjscie, m = self.sygnaly_od(dt.date.today().isoformat())
        self.assertEqual((m["claude_md_linie"], m["claude_md_linie_osobno"]), (2, 9))
        self.assertNotIn("dopisz katalog do `katalogi_regul_osobno`", (wyjscie / "podsumowanie.md").read_text(encoding="utf-8"))

    def test_transkrypcje_dodatkowe(self):
        self.zaloz_konto()
        inna = self.tmp / "laptop" / "projects" / "f-laptop"
        inna.mkdir(parents=True)
        (inna / "zdalna.jsonl").write_text("\n".join(json.dumps(r) for r in transkrypcja(str(self.inny), "z laptopa")) + "\n",
                                           encoding="utf-8")
        self.konfiguruj(transkrypcje_dodatkowe=[str(self.tmp / "laptop")])
        _, m = self.sygnaly_od(dt.date.today().isoformat())
        self.assertEqual(m["sesje"], 3)

    def test_naglowek_csv_zgodny_z_metrykami(self):
        _, m = self.sygnaly()
        naglowek = (SKRYPTY.parent / "assets" / "metryki-naglowek.csv").read_text(encoding="utf-8").split()[0].split(",")
        self.assertEqual(set(naglowek) - {"retro", "data", "zobowiazania_aktywne"}, set(m))
        stare = naglowek[:naglowek.index("zobowiazania_aktywne") + 1]
        self.assertEqual(len(stare), 33)                            # kolumny 0.1.2 bez zmian, nowe na końcu

    def test_dopisz_metryki_rozszerza_stary_naglowek(self):
        _, m = self.sygnaly()
        ws = self.tmp / "ws"
        stary = "retro,data,okno_od,sesje,zobowiazania_aktywne\nR00,2026-10-01,2026-09-30,3,4\n"
        (ws / "metryki.csv").write_text(stary, encoding="utf-8")
        wynik = json.loads(self.uruchom("dopisz_metryki.py", "--retro", "R01", "--zobowiazania", "5",
                                        "--katalog", str(ws), "--metryki", str(self.tmp / "wyn" / "metryki.json")))
        self.assertIn("koszt_api_usd", wynik["dopisane_kolumny"])
        self.assertEqual(wynik["wiersz"], "dopisany")
        self.uruchom("dopisz_metryki.py", "--retro", "R01", "--zobowiazania", "6", "--katalog", str(ws),
                     "--metryki", str(self.tmp / "wyn" / "metryki.json"))
        import csv
        with (ws / "metryki.csv").open(encoding="utf-8", newline="") as f:
            wiersze = list(csv.DictReader(f))
        self.assertEqual([w["retro"] for w in wiersze], ["R00", "R01"])  # ponowne uruchomienie zastępuje wiersz
        self.assertEqual(wiersze[0]["sesje"], "3")
        self.assertEqual(wiersze[0]["koszt_api_usd"], "")
        self.assertEqual(wiersze[1]["zobowiazania_aktywne"], "6")
        self.assertEqual(wiersze[1]["sesje"], str(m["sesje"]))


class Test014(Srodowisko):
    """Zmiany 0.1.4: trend tokenów tydzień po tygodniu, archiwum liczb, briefy innych sesji."""

    dopisz = TestSygnalyUzupelnienia.dopisz
    sygnaly = TestSygnalyUzupelnienia.sygnaly

    def trend_csv(self):
        import csv
        with (self.tmp / "ws" / "tokeny-tydzien.csv").open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))

    def test_trend_tygodniowy_i_archiwum(self):
        import tokeny
        cwd = str(self.inny)
        stary = dt.timedelta(days=-20)                   # inny tydzień niż „stara wiadomość” (-10 dni) z setUp
        czlowiek = {"type": "user", "timestamp": ts(stary), "cwd": cwd, "sessionId": "x", "origin": {"kind": "human"},
                    "message": {"content": "stara praca"}}
        self.dopisz("f-stare", "stara.jsonl", [czlowiek, wywolanie("o1", stary, wyj=1000, cwd=cwd),
                                               wywolanie("o2", stary + dt.timedelta(minutes=1), wyj=1000, cwd=cwd)])
        self.dopisz("f-nowe", "nowa.jsonl", [wywolanie("n1", dt.timedelta(minutes=-1), wyj=500, cwd=cwd)])
        self.zaloz_konto()
        tydzien_stary = tokeny.poniedzialek(dt.datetime.now().astimezone() + stary).isoformat()
        tydzien_biezacy = tokeny.poniedzialek(dt.date.today()).isoformat()
        # wiersz innego źródła i nieznana kolumna zostają nietknięte
        (self.tmp / "ws" / "tokeny-tydzien.csv").write_text(
            f"tydzien,zrodlo,wywolania_api,notatka\n{tydzien_stary},sandbox,77,ręcznie\n", encoding="utf-8")
        wyjscie, _ = self.sygnaly()
        wiersze = {(w["tydzien"], w["zrodlo"]): w for w in self.trend_csv()}
        self.assertEqual(wiersze[(tydzien_stary, "lokalne")]["wywolania_api"], "2")
        self.assertEqual(wiersze[(tydzien_stary, "lokalne")]["wiad_wlasciciela"], "1")
        self.assertEqual(wiersze[(tydzien_stary, "lokalne")]["koszt_api_usd"], "0.04")      # 2000 × $20/MTok
        self.assertEqual(wiersze[(tydzien_stary, "sandbox")]["notatka"], "ręcznie")
        self.assertEqual(wiersze[(tydzien_stary, "sandbox")]["wywolania_api"], "77")
        self.assertIn("okres niezakończony", wiersze[(tydzien_biezacy, "lokalne")]["pokrycie"])
        self.assertTrue((self.tmp / "ws" / "dane" / "tokeny-archiwum.json").is_file())
        podsumowanie = (wyjscie / "podsumowanie.md").read_text(encoding="utf-8")
        self.assertIn("## Trend tokenów", podsumowanie)
        self.assertIn("Źródło `sandbox`", podsumowanie)
        # retencja: transkrypcja znika, archiwum trzyma liczby, drugi przebieg nie dubluje wierszy
        (self.claude / "projects" / "f-stare" / "stara.jsonl").unlink()
        self.sygnaly()
        wiersze2 = self.trend_csv()
        self.assertEqual(len(wiersze2), len(wiersze))
        stary_lok = [w for w in wiersze2 if (w["tydzien"], w["zrodlo"]) == (tydzien_stary, "lokalne")][0]
        self.assertEqual((stary_lok["wywolania_api"], stary_lok["wiad_wlasciciela"]), ("2", "1"))

    def test_bez_trendu_i_przy_zawezeniu(self):
        self.zaloz_konto()
        wyjscie = self.tmp / "wyn"
        self.uruchom("sygnaly.py", "--od", dt.date.today().isoformat(), "--bez-gh", "--wyjscie", str(wyjscie), "--bez-trendu")
        self.uruchom("sygnaly.py", "--od", dt.date.today().isoformat(), "--bez-gh", "--wyjscie", str(wyjscie), "--projekt", "repo")
        self.assertFalse((self.tmp / "ws" / "tokeny-tydzien.csv").exists())
        self.assertFalse((self.tmp / "ws" / "dane" / "tokeny-archiwum.json").exists())
        self.assertIn("zawęża zakres", (wyjscie / "podsumowanie.md").read_text(encoding="utf-8"))

    def test_brief_innej_sesji_to_nie_wiadomosc_wlasciciela(self):
        pola = {"cwd": str(self.repo), "sessionId": "x", "timestamp": ts(), "origin": {"kind": "human"}}
        self.dopisz("f-repo", "sesja-repo.jsonl", [
            {"type": "user", **pola, "message": {"content": "Background (from the session that started this one):\nzrób X"}},
            {"type": "user", **pola, "message": {"content": "<system-reminder>x</system-reminder>"}},
        ])
        _, m = self.sygnaly()
        self.assertEqual(m["wiad_wlasciciela"], 2)

    def test_kierunek_trendu(self):
        import tokeny
        poniedzialki = [dt.date(2026, 6, 1) + dt.timedelta(weeks=i) for i in range(13)]
        wiersze = [{"tydzien": p.isoformat(), "zrodlo": "lokalne", "wywolania_api": "10",
                    "koszt_na_wiad": "1.0" if i < 8 else "2.0", "kontekst_mediana": "100000" if i < 8 else "70000",
                    "wybudzenia_koszt_usd": "0.5"} for i, p in enumerate(poniedzialki)]
        wiersze[-1]["koszt_na_wiad"] = "99"                         # tydzień bieżący, niezakończony: pomijany
        wiersze.append({"tydzien": poniedzialki[3].isoformat(), "zrodlo": "lokalne", "wywolania_api": "0"})
        wynik = {e: (k, n) for e, _, _, _, k, n in tokeny.trend(wiersze, dzis=poniedzialki[-1] + dt.timedelta(days=2))}
        self.assertEqual(wynik["koszt na wiadomość (USD)"], ("↑ pogorszenie", 8))
        self.assertEqual(wynik["mediana kontekstu sesji głównej"][0], "↓ poprawa")
        self.assertEqual(wynik["koszt wybudzeń (USD)"][0], "≈")
        self.assertEqual(wynik["kontekst startowy sesji"][0], "za mało danych")

    def test_trend_zachowuje_wiersz_z_wieksza_liczba_wywolan(self):
        import tokeny
        plik = self.tmp / "t.csv"
        plik.write_text("tydzien,wywolania_api,pokrycie\n2026-09-14,2618,\n", encoding="utf-8")   # bez kolumny zrodlo
        wynik = tokeny.zapisz_trend(plik, [{"tydzien": "2026-09-14", "zrodlo": "lokalne", "wywolania_api": 5, "pokrycie": ""},
                                           {"tydzien": "2026-09-21", "zrodlo": "lokalne", "wywolania_api": 7, "pokrycie": ""}])
        self.assertEqual([(w["tydzien"], str(w["wywolania_api"])) for w in wynik], [("2026-09-14", "2618"), ("2026-09-21", "7")])
        self.assertIn("z poprzedniego przebiegu", wynik[0]["pokrycie"])
        self.assertEqual(wynik[0]["zrodlo"], "lokalne")


class Test015(Srodowisko):
    """Zmiany 0.1.5: źródła zdalne trendu (polecenie, plik), obce wiersze trendu, `claude -p`."""

    dopisz = TestSygnalyUzupelnienia.dopisz
    sygnaly = TestSygnalyUzupelnienia.sygnaly
    trend_csv = Test014.trend_csv

    def zdalne_transkrypcje(self):
        """Katalog `projects` „innej maszyny”: sesja z wiadomością, briefem, zrzutem ekranu, `claude -p` i podagentem."""
        projekty = self.tmp / "zdalna" / "projects"
        folder = projekty / "-workspace"
        folder.mkdir(parents=True)
        cwd = "/workspace"
        czlowiek = lambda tresc, minuty, **inne: {  # noqa: E731
            "type": "user", "timestamp": ts(dt.timedelta(minutes=-minuty)), "cwd": cwd, "sessionId": "z",
            "origin": {"kind": "human"}, "message": {"content": tresc}, **inne}
        rekordy = [czlowiek("zrób to", 6), czlowiek("Background (from the session that started this one): x", 5),
                   czlowiek([{"type": "image", "source": {}}], 4), czlowiek("test hooka", 3, entrypoint="sdk-cli"),
                   wywolanie("z1", dt.timedelta(minutes=-2), wyj=1000, cwd=cwd),
                   wywolanie("z1", dt.timedelta(minutes=-2), wyj=10, cwd=cwd),
                   {"type": "cost-state", "totalCostUSD": 0.5}]
        (folder / "sesja-zdalna.jsonl").write_text("\n".join(json.dumps(r) for r in rekordy) + "\n", encoding="utf-8")
        pod = folder / "sesja-zdalna" / "subagents"
        pod.mkdir(parents=True)
        (pod / "agent-1.jsonl").write_text(json.dumps(wywolanie("z2", dt.timedelta(minutes=-1), wyj=1000, cwd=cwd)) + "\n",
                                           encoding="utf-8")
        return projekty

    def konfiguruj(self, **pola):
        plik = self.tmp / "ws" / "konfiguracja.json"
        konf = json.loads(plik.read_text(encoding="utf-8"))
        konf.update(pola)
        plik.write_text(json.dumps(konf), encoding="utf-8")

    def test_zbierz_liczby(self):
        projekty = self.zdalne_transkrypcje()
        wynik = json.loads(self.uruchom("zbierz_liczby.py", "--projekty", str(projekty)))
        self.assertEqual(sorted(wynik["calls"]), ["z1", "z2"])
        self.assertEqual(wynik["calls"]["z1"]["out"], 1000)                 # deduplikacja po message.id
        self.assertTrue(wynik["calls"]["z2"]["sub"])
        self.assertEqual(len(wynik["owner"]), 2)                            # tekst i zrzut ekranu; bez briefu i `claude -p`
        self.assertEqual(wynik["cost_state"], {"sesja-zd": 0.5})
        self.assertNotIn("zrób to", json.dumps(wynik, ensure_ascii=False))   # bez treści rozmów

    def test_zrodlo_zdalne_poleceniem(self):
        projekty = self.zdalne_transkrypcje()
        self.zaloz_konto()
        self.konfiguruj(zrodla_zdalne=[{"nazwa": "zdalny", "polecenie": [sys.executable, "-", "--projekty", str(projekty)]}])
        self.dopisz("f-repo", "sesja-repo.jsonl", [wywolanie("l1", dt.timedelta(minutes=-1), wyj=10, cwd=str(self.repo))])
        wyjscie, _ = self.sygnaly()
        biezacy = [w for w in self.trend_csv() if w["zrodlo"] == "zdalny"][-1]
        self.assertEqual((biezacy["wywolania_api"], biezacy["wiad_wlasciciela"], biezacy["koszt_api_usd"]), ("2", "2", "0.04"))
        self.assertTrue((self.tmp / "ws" / "dane" / "tokeny-archiwum-zdalny.json").is_file())
        podsumowanie = (wyjscie / "podsumowanie.md").read_text(encoding="utf-8")
        self.assertIn("`zdalny`: odczyt poleceniem, 2 wywołań w odczycie", podsumowanie)
        self.assertIn("Źródło `zdalny`", podsumowanie)
        self.assertTrue([w for w in self.trend_csv() if w["zrodlo"] == "lokalne"])   # lokalny trend bez zmian

    def test_zrodlo_z_pliku_blad_i_pominiecie(self):
        projekty = self.zdalne_transkrypcje()
        self.zaloz_konto()
        (self.tmp / "ws" / "dane").mkdir(exist_ok=True)
        (self.tmp / "ws" / "dane" / "liczby.json").write_text(
            self.uruchom("zbierz_liczby.py", "--projekty", str(projekty)), encoding="utf-8")
        self.konfiguruj(zrodla_zdalne=[{"nazwa": "sandbox", "plik": "dane/liczby.json"},
                                       {"nazwa": "padniety", "polecenie": [sys.executable, "-c", "import sys; sys.exit(3)"]},
                                       {"nazwa": "wylaczony", "plik": "x.json", "wlaczone": False}])
        wyjscie, _ = self.sygnaly()
        podsumowanie = (wyjscie / "podsumowanie.md").read_text(encoding="utf-8")
        self.assertIn("`sandbox`: plik `liczby.json` z ", podsumowanie)
        self.assertIn("`padniety`: **brak odczytu** (polecenie zwróciło 3", podsumowanie)
        self.assertNotIn("wylaczony", podsumowanie)
        self.assertEqual({w["zrodlo"] for w in self.trend_csv()}, {"sandbox"})     # sesje bazowe nie mają wywołań API
        self.uruchom("sygnaly.py", "--od", dt.date.today().isoformat(), "--bez-gh", "--wyjscie", str(wyjscie), "--bez-zdalnych")
        self.assertIn("`sandbox`: pominięte (`--bez-zdalnych`)", (wyjscie / "podsumowanie.md").read_text(encoding="utf-8"))

    def test_trend_zachowuje_obce_wiersze_i_uwagi(self):
        import tokeny
        plik = self.tmp / "t.csv"
        plik.write_text("tydzien,zrodlo,okno_od,wywolania_api,pokrycie,wiad_wlasciciela_sygnaly\n"
                        "2026-09-07,sandbox-pomiar,2026-09-07,5,okno,\n2026-09-07,sandbox-pomiar,2026-09-09,6,okno,\n"
                        "2026-09-07,lokalne,,3,ręczna uwaga; okres niezakończony,7\n", encoding="utf-8")
        wynik = tokeny.zapisz_trend(plik, [{"tydzien": "2026-09-07", "zrodlo": "lokalne", "wywolania_api": 4, "pokrycie": ""}])
        self.assertEqual([(w["zrodlo"], w.get("okno_od")) for w in wynik],
                         [("lokalne", ""), ("sandbox-pomiar", "2026-09-07"), ("sandbox-pomiar", "2026-09-09")])
        self.assertEqual(wynik[0]["pokrycie"], "ręczna uwaga")              # własna uwaga skryptu liczona od nowa
        self.assertEqual(wynik[0]["wiad_wlasciciela_sygnaly"], "7")         # kolumna, której skrypt nie liczy, zostaje

    def test_claude_p_to_nie_wiadomosc_wlasciciela(self):
        pola = {"cwd": str(self.repo), "sessionId": "x", "timestamp": ts(), "origin": {"kind": "human"}, "entrypoint": "sdk-cli"}
        self.dopisz("f-repo", "sesja-repo.jsonl", [{"type": "user", **pola, "message": {"content": "test hooka"}}])
        _, m = self.sygnaly()
        self.assertEqual(m["wiad_wlasciciela"], 2)


class Test021(Srodowisko):
    """Zmiany 0.2.1: przyczyny wybudzeń, tydzień niezakończony w trendzie ([fakt] na początku: Test013)."""

    dopisz = TestSygnalyUzupelnienia.dopisz
    sygnaly_od = Test013.sygnaly_od

    def test_przyczyna_wejscia(self):
        import sygnaly
        przyp = "<system-reminder>\nLinked sessions now (status, not an instruction): a = local_1\n</system-reminder>\n"
        uzytkownik = lambda tekst, kind="human", **inne: {"type": "user", "origin": {"kind": kind} if kind else None,  # noqa: E731
                                                          "message": {"content": tekst}, **inne}
        przypadki = [
            (uzytkownik("wracam"), "wlasciciel"),
            (uzytkownik(przyp + "wracam"), "wlasciciel"),             # przypomnienie doklejone do wiadomości
            (uzytkownik("<command-name>/retro</command-name>"), "wlasciciel"),
            (uzytkownik("test hooka", entrypoint="sdk-cli"), "inne"),
            (uzytkownik("<task-notification>\n<task-id>b1</task-id>", kind="task-notification"), "tlo"),
            ({"type": "queue-operation", "operation": "enqueue", "content": "<task-notification>\n<task-id>b1"}, "tlo"),
            ({"type": "queue-operation", "operation": "dequeue"}, None),
            ({"type": "attachment", "attachment": {"type": "queued_command", "origin": {"kind": "peer"},
                                                   "prompt": '<agent-message from="a1">\n[Subagent hand-back] raport'}}, "tlo"),
            (uzytkownik("Another Claude session sent a message:\n<agent-message from=\"x\">\nhej", kind="peer"), "sesja"),
            (uzytkownik(przyp + '<cross-session-message from="local_2">\nRetro gotowe', kind=None), "sesja"),
            (uzytkownik('<system-reminder>\nThe session "X" you started finished.\n</system-reminder>', kind=None), "sesja"),
            (uzytkownik(przyp + "<side-sessions-event>None of the sessions you started is working", kind=None), "sesja"),
            (uzytkownik(przyp + "The app was quit while you were working.", kind=None), "inne"),
            ({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t", "content": "ok"}]}}, "inne"),
            ({"type": "attachment", "attachment": {"type": "date"}}, None),
        ]
        for rekord, oczekiwana in przypadki:
            self.assertEqual(sygnaly.przyczyna_wejscia(rekord), oczekiwana, rekord)

    def test_wybudzenia_wg_przyczyny(self):
        self.zaloz_konto()
        cwd = str(self.inny)
        h = lambda godz, minuty=0: dt.timedelta(hours=-godz, minutes=-minuty)  # noqa: E731
        pola = {"cwd": cwd, "sessionId": "x"}
        wejscia = {
            "wlasciciel": [{"type": "user", "timestamp": ts(h(1, 1)), **pola, "origin": {"kind": "human"}, "message": {
                "content": "<system-reminder>\nLinked sessions now: a\n</system-reminder>\nco dalej?"}}],
            "tlo": [{"type": "queue-operation", "operation": "enqueue", "timestamp": ts(h(1, 2)), **pola,
                     "content": "<task-notification>\n<task-id>b1</task-id>"},
                    {"type": "user", "timestamp": ts(h(1, 1)), **pola, "origin": {"kind": "task-notification"},
                     "message": {"content": "<task-notification>\n<task-id>b1</task-id>"}},
                    # wiadomość właściciela po powiadomieniu: sesję obudziło to, co przyszło pierwsze
                    {"type": "user", "timestamp": ts(h(1, 0.5)), **pola, "origin": {"kind": "human"},
                     "message": {"content": "a to?"}}],
            "podagent": [{"type": "attachment", "timestamp": ts(h(1, 1)), **pola, "attachment": {
                "type": "queued_command", "origin": {"kind": "peer"},
                "prompt": '<agent-message from="a1">\n[Subagent hand-back] raport'}}],
            "sesja": [{"type": "user", "timestamp": ts(h(1, 1)), **pola, "message": {
                "content": '<cross-session-message from="local_2">\nRetro gotowe'}}],
            "inne": [{"type": "user", "timestamp": ts(h(1, 1)), **pola, "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "moved to the background"}]}}],
        }
        for nazwa, rekordy in wejscia.items():
            self.dopisz("f-wyb", f"{nazwa}.jsonl", [wywolanie(f"{nazwa}-1", h(5), wyj=10, cwd=cwd), *rekordy,
                                                    wywolanie(f"{nazwa}-2", h(1), z1h=100000, cwd=cwd)])
        wyjscie, m = self.sygnaly_od((dt.date.today() - dt.timedelta(days=1)).isoformat())
        self.assertEqual(m["wybudzenia"], 5)
        self.assertEqual((m["wybudzenia_wlasciciel"], m["wybudzenia_tlo"], m["wybudzenia_sesja"], m["wybudzenia_inne"]),
                         (1, 2, 1, 1))
        podsumowanie = (wyjscie / "podsumowanie.md").read_text(encoding="utf-8")
        self.assertIn("`tlo` po 4.0 h: zapis 100k, $0.80; obudziło: zadanie lub podagent w tle", podsumowanie)
        self.assertIn("`sesja` po 4.0 h: zapis 100k, $0.80; obudziło: inna sesja", podsumowanie)
        self.assertIn("Kto obudził sesję (pierwsze wejście po przerwie): wiadomość właściciela 1, "
                      "zadanie lub podagent w tle 2, inna sesja 1, inne (np. wynik narzędzia po długim czekaniu) 1.",
                      podsumowanie)

    def trend_wiersze(self, dzis, biezacy=True):
        import tokeny
        start = tokeny.poniedzialek(dzis)
        wiersze = [{"tydzien": (start - dt.timedelta(weeks=i)).isoformat(), "zrodlo": "lokalne", "wywolania_api": "10",
                    "kontekst_startowy_mediana": "72000", "koszt_na_wiad": "1.0", "koszt_api_usd": "100"}
                   for i in range(12, 0, -1)]
        if biezacy:
            wiersze.append({"tydzien": start.isoformat(), "zrodlo": "lokalne", "wywolania_api": "5",
                            "kontekst_startowy_mediana": "55000", "koszt_na_wiad": "1.5", "koszt_api_usd": "40"})
        return wiersze

    def test_tydzien_niezakonczony(self):
        import tokeny
        dzis = dt.date(2026, 10, 24)                                # sobota tygodnia 10-19
        self.assertEqual(tokeny.tydzien_niezakonczony(self.trend_wiersze(dzis), dzis=dzis)[0], "2026-10-19")
        self.assertEqual(tokeny.tydzien_niezakonczony(self.trend_wiersze(dzis), dzis=dzis)[1]["kontekst_startowy_mediana"],
                         55000)
        self.assertIsNone(tokeny.tydzien_niezakonczony(self.trend_wiersze(dzis, biezacy=False), dzis=dzis))
        pusty = self.trend_wiersze(dzis)
        pusty[-1]["wywolania_api"] = "0"
        self.assertIsNone(tokeny.tydzien_niezakonczony(pusty, dzis=dzis))
        self.assertIsNone(tokeny.tydzien_niezakonczony(self.trend_wiersze(dzis), zrodlo="sandbox", dzis=dzis))
        # niedziela kończy tydzień, ale dopiero od poniedziałku wchodzi on do porównania
        self.assertEqual(tokeny.tydzien_niezakonczony(self.trend_wiersze(dzis), dzis=dt.date(2026, 10, 25))[0], "2026-10-19")
        self.assertEqual((tokeny.strzalka(72000, 55000), tokeny.strzalka(1.0, 1.5), tokeny.strzalka(1.0, 1.1),
                          tokeny.strzalka(0, 0), tokeny.strzalka(None, 1)), ("↓", "↑", "≈", "≈", ""))

    def test_trend_pokazuje_tydzien_niezakonczony(self):
        import sygnaly
        import teksty
        teksty.ustaw("pl")
        dzis = dt.date.today()
        linie = "\n".join(sygnaly.raport_trendu(self.trend_wiersze(dzis), ""))
        tydzien = self.trend_wiersze(dzis)[-1]["tydzien"][5:]
        self.assertIn(f"| kierunek | tydzień {tydzien} (niezakończony) |\n|---|---|---|---|---|---|", linie)
        self.assertIn("| ≈ | 55k ↓ |", linie)                     # świeża poprawka widoczna od razu
        self.assertIn("| koszt na wiadomość (USD) |", linie)
        self.assertIn("| ≈ | 1.5 ↑ |", linie)
        self.assertIn("| koszt tygodnia (USD) | 100 (8) |", linie)
        self.assertIn("| ≈ | 40 |", linie)                         # suma tygodnia jeszcze rośnie: bez „↓”
        self.assertIn("| — |", linie)                              # wskaźnik bez danych w bieżącym tygodniu
        self.assertIn("Ostatnia kolumna: bieżący tydzień", linie)
        bez = "\n".join(sygnaly.raport_trendu(self.trend_wiersze(dzis, biezacy=False), ""))
        self.assertNotIn("niezakończony)", bez)
        self.assertIn("| kierunek |\n|---|---|---|---|---|\n", bez)


AGENT_PROG, AGENT_PRZEGLAD, AGENT_CI = "a1b2c3d4e5f60718", "b2c3d4e5f6071829", "c3d4e5f60718293a"


def praca_agentow(cwd: str) -> list:
    """Sesja: programista na PR #12, przegląd NO-GO, kontynuacja programisty, CI czerwone, kontynuacja, przegląd GO."""
    pola = {"cwd": cwd, "sessionId": "x"}
    minuta = lambda n: ts(dt.timedelta(minutes=-60 + n))  # noqa: E731

    def start(n, tid, typ, opis, agent, model, raport):
        return [{"type": "assistant", "timestamp": minuta(n), **pola, "message": {"model": "claude-opus-5-5", "content": [
                    {"type": "tool_use", "id": tid, "name": "Agent",
                     "input": {"subagent_type": typ, "description": opis, "prompt": "zrób to"}}]}},
                {"type": "user", "timestamp": minuta(n + 1), **pola,
                 "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "content": [{"type": "text", "text": raport}]}]},
                 "toolUseResult": {"agentId": agent, "resolvedModel": model, "isAsync": False,
                                   "content": [{"type": "text", "text": raport}]}}]

    def kontynuacja(n, tid, agent, tekst):
        return [{"type": "assistant", "timestamp": minuta(n), **pola, "message": {"model": "claude-opus-5-5", "content": [
            {"type": "tool_use", "id": tid, "name": "SendMessage", "input": {"to": agent, "message": tekst}}]}}]

    return (start(1, "g1", "programista", "PR #12: hook", AGENT_PROG, "claude-opus-5-5", "Gotowe, PR #12 otwarty.")
            + start(5, "g2", "przeglad-mechaniczny", "Przegląd PR #12", AGENT_PRZEGLAD, "claude-sonnet-5-5",
                    "Verdict: NO-GO. 2 blocking findings.")
            + kontynuacja(9, "g3", AGENT_PROG, "Popraw PR #12 wg przeglądu")
            + start(12, "g4", "obserwator-ci", "CI PR #12", AGENT_CI, "claude-haiku-5-5",
                    "- 39488962325 (PR #12, feat/hook): failure")
            + kontynuacja(15, "g5", AGENT_PROG, "PR #12: czerwone CI")
            + start(20, "g6", "przeglad-mechaniczny", "Przegląd PR #12", AGENT_PRZEGLAD, "claude-sonnet-5-5",
                    "**Można scalić: tak.** Bez blokerów."))


class Test030(Srodowisko):
    """Zmiany 0.3.0: tokeny i efektywność pisania (role, zdarzenia agentów, rundy poprawek, porównanie)."""

    dopisz = TestSygnalyUzupelnienia.dopisz
    sygnaly = TestSygnalyUzupelnienia.sygnaly

    def test_werdykt_i_ci(self):
        import zdarzenia_agentow as za
        werdykty = [
            ("Verdict: NO-GO. Two blocking findings.", "negatywny"),
            ("Verdict: **FIX** before merge", "negatywny"),
            ("Werdykt: do poprawy (2 uwagi)", "negatywny"),
            ("Można scalić: nie. Bloker: brak testu.", "negatywny"),
            ("This PR is not ready to merge: the hook is bypassed.", "negatywny"),
            ("Verdict: GO, with 3 minor findings. None of them blocks the merge.", "pozytywny"),
            ("Verdict: MERGE. I found nothing to fix.", "pozytywny"),
            ("Przegląd PR #963: żadne znalezisko nie blokuje merge'a, są dwie uwagi.", "pozytywny"),
            ("**Można scalić: tak.** Wszystkie siedem sprawdzeń zielone, bez blokerów.", "pozytywny"),
            ("Run 1: success. Nothing else.", None),
        ]
        for tekst, oczekiwany in werdykty:
            self.assertEqual(za.werdykt(tekst)[0], oczekiwany, tekst)
        self.assertEqual(za.werdykt("Verdict: GO, with 3 minor findings.")[1], 3)
        for tekst, oczekiwany in [
                ("Run 39488962325 (PR #968, branch x): conclusion failure.", [[968, "porazka"]]),
                ("- 39491798179 (PR #969, chore/x): cancelled, brak failed jobs", [[969, "anulowane"]]),
                ("- 39491573821 (PR #968, chore/y): success", [[968, "sukces"]])]:
            self.assertEqual(za.ci_wyniki(tekst), oczekiwany, tekst)
        self.assertEqual(za.prs("PR #5, github.com/w/r/pull/77 i #1203; kolor #12ab34"), [5, 77, 1203])

    def test_role_i_rodziny(self):
        import efektywnosc as ef
        wz = ef.wzorce_rol({})
        role = {a: ef.rola(True, a, wz) for a in ("programista", "programista-prosty", "przeglad-mechaniczny",
                                                    "architekt-przeglad", "obserwator-ci", "architekt", "Explore",
                                                    "code-reviewer", "general-purpose")}
        self.assertEqual(role, {"programista": "implementacja", "programista-prosty": "implementacja",
                                "przeglad-mechaniczny": "przeglad", "architekt-przeglad": "przeglad",
                                "obserwator-ci": "ci", "architekt": "architekt", "Explore": "inne",
                                "code-reviewer": "przeglad", "general-purpose": "inne"})
        self.assertEqual(ef.rola(False, "programista", wz), "sesja")
        wlasne = ef.wzorce_rol({"role_agentow": {"implementacja": ["^builder"], "przeglad": ["checker"]}})
        self.assertEqual((ef.rola(True, "builder-x", wlasne), ef.rola(True, "programista", wlasne),
                          ef.rola(True, "checker", wlasne)), ("implementacja", "inne", "przeglad"))
        self.assertEqual([ef.rodzina(m) for m in ("claude-opus-5-5[1m]", "claude-fable-5-1", "claude-haiku-4-5", None)],
                         ["Opus", "Fable", "Haiku", "?"])
        import collections
        self.assertEqual(ef.udzialy(collections.Counter({"Opus": 3, "Sonnet": 1})), "Opus:75;Sonnet:25")
        self.assertIsNone(ef.udzialy(collections.Counter()))

    def zapisz_agentow(self):
        self.dopisz("f-repo", "sesja-repo.jsonl", praca_agentow(str(self.repo))
                    + [wywolanie("g0", dt.timedelta(minutes=-61), wyj=100, cwd=str(self.repo))])
        pod = self.claude / "projects" / "f-repo" / "sesja-repo" / "subagents"
        pod.mkdir(parents=True)
        (pod / f"agent-{AGENT_PROG}.meta.json").write_text(json.dumps({"agentType": "programista"}), encoding="utf-8")
        (pod / f"agent-{AGENT_PROG}.jsonl").write_text(json.dumps(wywolanie(
            "p1", dt.timedelta(minutes=-58), wyj=1000, cwd=str(self.repo))) + "\n", encoding="utf-8")   # $0.02

    def test_powroty_z_transkrypcji_i_przez_stdin(self):
        import efektywnosc as ef
        import zdarzenia_agentow as za
        self.zapisz_agentow()
        dane = za.zbierz([self.claude / "projects"], (dt.date.today() - dt.timedelta(days=1)).isoformat())
        self.assertEqual([z["rodzaj"] for z in dane["zdarzenia"] if z["s"] == "sesja-re"],
                         ["start", "raport", "start", "raport", "kontynuacja", "start", "raport", "kontynuacja",
                          "start", "raport"])
        self.assertEqual(dane["agenci"][AGENT_PROG[:12]]["tokeny"]["out"], 1000)
        self.assertNotIn("Verdict", json.dumps(dane))                   # treść raportów nie trafia do wyniku
        od = dt.datetime.now().astimezone() - dt.timedelta(days=1)
        stat, przyczyny = ef.powroty(dane, ef.wzorce_rol({}), od, od + dt.timedelta(days=2))
        self.assertEqual(stat[("programista", "Opus")],
                         {"uruchomienia": 1, "przeglady": 2, "przeglady_neg": 1, "ci": 1, "ci_porazki": 1, "powroty": 2})
        self.assertEqual(dict(przyczyny), {"przeglad": 1, "ci": 1})
        # samodzielnie przez stdin (jak w kontenerze); --od filtruje
        skrypt = (SKRYPTY / "zdarzenia_agentow.py").read_bytes()
        r = subprocess.run([sys.executable, "-", "--projekty", str(self.claude / "projects"), "--od", "2000-01-01"],
                           input=skrypt, capture_output=True, cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(json.loads(r.stdout)["zdarzenia"]), 10)
        r = subprocess.run([sys.executable, "-", "--projekty", str(self.claude / "projects"),
                            "--od", (dt.date.today() + dt.timedelta(days=2)).isoformat()],
                           input=skrypt, capture_output=True, cwd=self.tmp)
        self.assertEqual(json.loads(r.stdout)["zdarzenia"], [])

    def test_rundy_pr(self):
        import efektywnosc as ef
        teraz = dt.datetime(2026, 10, 22, 12, 0, tzinfo=dt.timezone.utc)
        iso = lambda h: (teraz + dt.timedelta(hours=h)).isoformat().replace("+00:00", "Z")  # noqa: E731
        commit = lambda h, modele, naglowek="feat", rodzice=1: {  # noqa: E731
            "ts": iso(h), "naglowek": naglowek, "scalenie": rodzice > 1, "modele": modele}
        lista = [
            {"repo": "w/r", "pr": 1, "utworzony": iso(-5), "scalony": iso(0), "galaz": "feat/a", "commitow": 4, "commity": [
                commit(-5, ["Opus"]), commit(-4.9, ["Opus"]), commit(-3, [], "Merge branch 'main'", 2),
                commit(-2, ["Sonnet"])]},
            {"repo": "w/r", "pr": 2, "utworzony": iso(-3), "scalony": iso(-1), "galaz": "feat/b", "commitow": 1,
             "commity": [commit(-3, ["Fable"])]},
            {"repo": "w/r", "pr": 3, "utworzony": iso(-3), "scalony": iso(-1), "galaz": "integration/x", "commitow": 2,
             "commity": [commit(-3, ["Opus"]), commit(-1, ["Opus"])]},
            {"repo": "w/r", "pr": 4, "utworzony": iso(-3), "scalony": iso(-1), "galaz": "feat/c", "commitow": 41,
             "commity": [commit(-3, ["Opus"])]},
            {"repo": "w/r", "pr": 5, "utworzony": iso(-9), "scalony": iso(-1), "galaz": "feat/d", "commitow": 3,
             "commity": [commit(-9, []), commit(-8, []), commit(-7, ["Opus"])]},
        ]
        rundy = {r["pr"]: r for r in ef.rundy_pr(lista, {})}
        self.assertEqual(sorted(rundy), [1, 2, 5])                    # gałąź integracyjna i PR > 40 commitów pominięte
        self.assertEqual((rundy[1]["autor"], rundy[1]["rundy"], rundy[1]["commity"]), ("Opus", 1, 3))
        self.assertEqual(rundy[1]["poprawki"], {("Opus", "Sonnet"): 1})
        self.assertEqual((rundy[2]["autor"], rundy[2]["rundy"]), ("Fable", 0))
        self.assertEqual((rundy[5]["autor"], rundy[5]["rundy"]), (None, 2))
        self.assertEqual(ef.opis_pr(list(rundy.values())),
                         {"pr": 3, "z_poprawka": 66.7, "rundy": 1.0, "commity": 2.3, "h": 5.0})
        self.assertEqual(sorted(r["pr"] for r in ef.rundy_pr(lista, {"pr_pomin_galezie": [], "pr_przerwa_rundy_min": 180})),
                         [1, 2, 3, 5])
        self.assertEqual(ef.rundy_pr(lista, {"pr_przerwa_rundy_min": 180})[0]["rundy"], 0)

    def test_porownanie_z_poprzednimi_retro(self):
        import efektywnosc as ef
        import teksty
        teksty.ustaw("pl")
        plik = self.tmp / "metryki.csv"
        plik.write_text("retro,okno_od,okno_od_godzina,koszt_na_wiadomosc_usd,pr_z_poprawka_proc\n"
                        "R01,2026-10-01,00:00,9,90\nR02,2026-10-05,10:00,1.0,10\nR03,2026-10-09,10:00,2.0,20\n"
                        "R04,2026-10-13,10:00,3.0,30\nR05,2026-10-17,10:00,99,99\n", encoding="utf-8")
        etykiety, wiersze = ef.porownanie(plik, {"okno_od": "2026-10-17", "okno_od_godzina": "10:00",
                                                 "koszt_na_wiadomosc_usd": 1.0, "pr_z_poprawka_proc": 50})
        self.assertEqual(etykiety, ["R02", "R03", "R04"])           # bez wiersza tego samego okna
        wynik = {k: (w, teraz, kier) for k, w, teraz, kier in wiersze}
        self.assertEqual(wynik["pr_z_poprawka_proc"], ([10, 20, 30], 50, "↑ pogorszenie"))
        self.assertEqual(wynik["koszt_na_wiadomosc_usd"][2], "↓ poprawa")
        self.assertEqual(wynik["powroty_ci"], ([None, None, None], None, "—"))
        self.assertEqual(ef.porownanie(self.tmp / "brak.csv", {}), ([], []))

    def falszywy_gh(self):
        """`gh` w teście: repo `w/r`, jedna strona wyszukiwania scalonych PR, puste listy PR i CI."""
        teraz = dt.datetime.now(dt.timezone.utc)
        iso = lambda minuty: (teraz + dt.timedelta(minutes=minuty)).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
        commit = lambda m, model, naglowek="feat": {"commit": {  # noqa: E731
            "oid": "x", "authoredDate": iso(m), "messageHeadline": naglowek, "parents": {"totalCount": 1},
            "messageBody": f"Opis\n\nCo-Authored-By: Claude {model} <noreply@anthropic.com>" if model else "Opis"}}
        pr = lambda n, galaz, commity: {"number": n, "createdAt": iso(-300), "mergedAt": iso(-5), "headRefName": galaz,  # noqa: E731
                                        "commits": {"totalCount": len(commity), "nodes": commity}}
        odpowiedz = {"data": {"search": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": [
            pr(12, "feat/hook", [commit(-300, "Opus 5.5"), commit(-120, "Opus 5.5", "fix: przegląd")]),
            pr(13, "feat/docs", [commit(-60, "Sonnet 5.5")]), {}]}}}
        (self.tmp / "gh-odpowiedz.json").write_text(json.dumps(odpowiedz), encoding="utf-8")
        kod = ("import json, sys\na = sys.argv[1:]\n"
               "if a[:2] == ['repo', 'view']: print('w/r')\n"
               f"elif a[:2] == ['api', 'graphql']: print(open(r'{self.tmp / 'gh-odpowiedz.json'}', encoding='utf-8').read())\n"
               "else: print('[]')\n")
        (self.tmp / "gh_falszywy.py").write_text(kod, encoding="utf-8")
        if os.name == "nt":
            gh = self.tmp / "gh.cmd"
            gh.write_text(f'@"{sys.executable}" "{self.tmp / "gh_falszywy.py"}" %*\n', encoding="utf-8")
        else:
            gh = self.tmp / "gh"
            gh.write_text(f"#!{sys.executable}\n" + kod, encoding="utf-8")
            gh.chmod(0o755)
        return str(gh)

    def test_sekcja_efektywnosci_w_podsumowaniu(self):
        self.zapisz_agentow()
        subprocess.run(["git", "-C", str(self.repo), "remote", "add", "origin", "https://example.com/w/r.git"], check=True)
        gh = self.falszywy_gh()
        self.zaloz_konto()
        ws = self.tmp / "ws"
        konf = json.loads((ws / "konfiguracja.json").read_text(encoding="utf-8"))
        konf["gh"] = gh
        (ws / "konfiguracja.json").write_text(json.dumps(konf), encoding="utf-8")
        (ws / "metryki.csv").write_text("retro,okno_od,okno_od_godzina,pr_z_poprawka_proc,powroty_przeglad\n"
                                        "R01,2026-01-01,00:00,10,0\nR02,2026-01-05,00:00,20,0\n", encoding="utf-8")
        wyjscie = self.tmp / "wyn"
        self.uruchom("sygnaly.py", "--od", dt.date.today().isoformat(), "--wyjscie", str(wyjscie))
        m = json.loads((wyjscie / "metryki.json").read_text(encoding="utf-8"))
        self.assertEqual((m["pr_analizowane"], m["pr_z_poprawka_proc"], m["rundy_na_pr"]), (2, 50.0, 0.5))
        self.assertEqual((m["pr_wg_modelu"], m["pr_z_poprawka_proc_wg_modelu"]), ("Opus:50;Sonnet:50", "Opus:100;Sonnet:0"))
        self.assertEqual((m["powroty_przeglad"], m["powroty_ci"]), (1, 1))
        self.assertEqual(m["koszt_implementacji_proc_wg_modelu"], "Opus:100")
        p = (wyjscie / "podsumowanie.md").read_text(encoding="utf-8")
        self.assertIn("## Tokeny i efektywność pisania", p)
        self.assertIn("| pr_z_poprawka_proc | 10 | 20 | 50 | **↑ pogorszenie** |", p)
        self.assertIn("| implementacja · Opus |", p)                    # koszt wg roli z archiwum (typ podagenta)
        self.assertIn("| sesja główna · Opus |", p)
        self.assertIn("| Opus | 1 | 100% | 1 | 2 |", p)                 # rundy wg modelu autora
        self.assertIn("Opus → Opus: 1", p)
        self.assertIn("| programista · Opus | 1 | 2 (1) | 1 (1) | 2 |", p)
        self.assertIn("Powroty wg przyczyny: przegląd 1, CI 1.", p)
        arch = json.loads((ws / "dane" / "tokeny-archiwum.json").read_text(encoding="utf-8"))
        self.assertEqual(arch["calls"]["p1"]["agent"], "programista")
        # bez gh: rundy pominięte, metryki puste
        self.uruchom("sygnaly.py", "--od", dt.date.today().isoformat(), "--wyjscie", str(wyjscie), "--bez-gh")
        m = json.loads((wyjscie / "metryki.json").read_text(encoding="utf-8"))
        self.assertIsNone(m["pr_z_poprawka_proc"])
        self.assertIn("Rundy poprawek pominięte", (wyjscie / "podsumowanie.md").read_text(encoding="utf-8"))

    def test_zdarzenia_ze_zrodla_zdalnego(self):
        self.zaloz_konto()
        ws = self.tmp / "ws"
        inny = self.tmp / "zdalne" / "projects"
        (inny / "f-x").mkdir(parents=True)
        (inny / "f-x" / "zdalna.jsonl").write_text(
            "\n".join(json.dumps(r) for r in praca_agentow("/workspace")) + "\n", encoding="utf-8")
        konf = json.loads((ws / "konfiguracja.json").read_text(encoding="utf-8"))
        konf["zrodla_zdalne"] = [
            {"nazwa": "kontener", "zdarzenia_polecenie": [sys.executable, "-", "--projekty", str(inny)]},
            {"nazwa": "zepsute", "zdarzenia_plik": "dane/nie-ma.json"}]
        (ws / "konfiguracja.json").write_text(json.dumps(konf), encoding="utf-8")
        wyjscie = self.tmp / "wyn"
        self.uruchom("sygnaly.py", "--od", dt.date.today().isoformat(), "--bez-gh", "--wyjscie", str(wyjscie))
        p = (wyjscie / "podsumowanie.md").read_text(encoding="utf-8")
        self.assertIn("Zdarzenia agentów `kontener`: odczyt poleceniem, 10 zdarzeń.", p)
        self.assertIn("Zdarzenia agentów `zepsute`: **brak odczytu**", p)
        self.assertIn("### Powroty od przeglądu i CI w transkrypcjach: `kontener`", p)
        m = json.loads((wyjscie / "metryki.json").read_text(encoding="utf-8"))
        self.assertEqual((m["powroty_przeglad"], m["powroty_ci"]), (1, 1))   # lokalnie brak, z kontenera 1 + 1


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
        self.uruchom("zaloz.py", "--tryb", "projekt", "--repo", str(self.repo), "--jezyk", "pl")
        self.assertIn("w tym projekcie", self.hook(self.repo / "pod")["systemMessage"])
        self.assertIsNone(self.hook(self.inny))


class TestJezyki(Srodowisko):
    def test_zaloz_po_angielsku(self):
        wynik = self.zaloz_konto("en")
        ws = self.tmp / "ws"
        self.assertEqual(json.loads((ws / "konfiguracja.json").read_text(encoding="utf-8"))["jezyk"], "en")
        self.assertIn("Commitments register", (ws / "zobowiazania.md").read_text(encoding="utf-8"))
        self.assertTrue(wynik["szablon_retro"].replace("\\", "/").endswith("assets/en/szablon-retro.md"))
        self.assertEqual(wynik["uwagi"], [])

    def test_zaloz_jezyk_bez_szablonow(self):
        wynik = self.zaloz_konto("de")
        self.assertEqual(wynik["jezyk"], "de")
        self.assertIn("`de`", wynik["uwagi"][0])
        self.assertIn("Commitments register", (self.tmp / "ws" / "zobowiazania.md").read_text(encoding="utf-8"))

    def test_konfiguracja_bez_pola_jezyk_po_polsku(self):
        self.zaloz_konto("en")
        plik = self.tmp / "ws" / "konfiguracja.json"
        konf = json.loads(plik.read_text(encoding="utf-8"))
        del konf["jezyk"]                                     # katalog sprzed 0.2.0
        plik.write_text(json.dumps(konf), encoding="utf-8")
        self.assertEqual(wspolne.wczytaj_konfiguracje(self.tmp / "ws")["jezyk"], "pl")

    def test_sygnaly_po_angielsku(self):
        self.zaloz_konto("en")
        wyjscie = self.tmp / "wyn"
        self.uruchom("sygnaly.py", "--od", dt.date.today().isoformat(), "--bez-gh", "--wyjscie", str(wyjscie))
        podsumowanie = (wyjscie / "podsumowanie.md").read_text(encoding="utf-8")
        self.assertIn("# Retro signals:", podsumowanie)
        self.assertIn("## Tokens and cost", podsumowanie)
        self.assertIn("## Token trend", podsumowanie)
        os_czasu = (wyjscie / "repo.md").read_text(encoding="utf-8")
        self.assertIn("**Owner:**", os_czasu)
        self.assertIn("**wlasna:** zrób inaczej", os_czasu)    # klasy odpowiedzi to identyfikatory
        m = json.loads((wyjscie / "metryki.json").read_text(encoding="utf-8"))
        self.assertEqual(m["pyt_rekomendowana"], 2)             # „(rekomendowane)” rozpoznane też przy jezyk=en

    def test_status_zakonczone_w_wielu_jezykach(self):
        self.zaloz_konto("en")
        for status in ("completed", "zakończone", "Done"):
            plik = self.tmp / "ws" / "retro" / "R00-2026-10-08.md"
            plik.write_text(f"# R00\n\n**Status:** {status}\n", encoding="utf-8")
            self.assertIsNone(self.hook(self.inny, "2026-10-14"), status)
        plik.write_text("# R00\n\n**Status:** draft\n", encoding="utf-8")
        self.assertIn("Retro overdue", self.hook(self.inny, "2026-10-14")["systemMessage"])

    def test_okno_od_commita_zakonczenia_po_angielsku(self):
        self.zaloz_konto("en")
        ws = self.tmp / "ws"
        plik = ws / "retro" / f"R00-{dt.date.today().isoformat()}.md"
        plik.write_text("# R00\n\n**Status:** completed\n", encoding="utf-8")
        for polecenie in (["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "retro(R00)"]):
            subprocess.run(["git", *polecenie], cwd=ws, check=True, capture_output=True)
        wyjscie = self.tmp / "wyn"
        self.uruchom("sygnaly.py", "--od", dt.date.today().isoformat(), "--bez-gh", "--wyjscie", str(wyjscie))
        self.assertIn("from the commit that completed R00", (wyjscie / "podsumowanie.md").read_text(encoding="utf-8"))

    def hook(self, cwd, dzis=None):
        argumenty = ["--dzis", dzis] if dzis else []
        out = self.uruchom("przypomnienie.py", *argumenty, wejscie=json.dumps({"cwd": str(cwd)}))
        return json.loads(out) if out.strip() else None


class TestRozpoznawanieJezyka(unittest.TestCase):
    def test_rekomendacja(self):
        import teksty
        for etykieta in ("Tak (rekomendowane)", "Yes (Recommended)", "Sí (recomendado)", "Oui (recommandé)",
                         "Ja (empfohlen)", "Sì (raccomandato)", "Ja (aanbevolen)", "Tak — zalecam"):
            self.assertTrue(teksty.WZOR_REKOMENDACJI.search(etykieta), etykieta)
        for etykieta in ("Nie zalecane", "Not recommended", "No recomendado", "Nicht empfohlen", "Inna opcja"):
            self.assertFalse(teksty.WZOR_REKOMENDACJI.search(etykieta), etykieta)

    def test_pytanie_o_fakt(self):
        import sygnaly
        q = {"question": "[fact] Which network are you on?", "options": [{"label": "Home"}, {"label": "Office"}]}
        self.assertEqual(sygnaly.klasyfikuj_odpowiedz("hotel wifi", q), "fakt")
        q["question"] = "\n [FAKT] W jakiej sieci jesteś?"
        self.assertEqual(sygnaly.klasyfikuj_odpowiedz("hotel", q), "fakt")
        # 0.2.1: znacznik tylko na początku; w cytacie albo na końcu to zwykłe pytanie
        for pytanie in ("W jakiej sieci jesteś? [fakt]", "Hook każe dopisać „[fakt]”: zmieniamy?"):
            q["question"] = pytanie
            self.assertEqual(sygnaly.klasyfikuj_odpowiedz("hotel", q), "wlasna", pytanie)

    def test_korekta_wg_jezyka(self):
        import teksty
        self.assertTrue(teksty.wzor_korekty("pl").search("dlaczego znowu?"))
        self.assertTrue(teksty.wzor_korekty("pl").search("why again?"))      # angielskie zawsze
        self.assertTrue(teksty.wzor_korekty("en").search("That's not what I asked"))
        self.assertFalse(teksty.wzor_korekty("en").search("dlaczego znowu?"))

    def test_teksty_kompletne(self):
        import teksty
        for klucz, wpis in teksty.TEKSTY.items():
            self.assertEqual(set(wpis), set(teksty.JEZYKI), klucz)

    def test_nic_nie_przeslania_t(self):
        """Zmienna albo argument `t` w funkcji przesłania teksty.t (TypeError dopiero na rzadkiej ścieżce)."""
        import ast
        for plik in SKRYPTY.glob("*.py"):
            drzewo = ast.parse(plik.read_text(encoding="utf-8"))
            if not any(isinstance(w, ast.ImportFrom) and w.module == "teksty" and any(a.name == "t" for a in w.names)
                       for w in ast.walk(drzewo)):
                continue
            for w in ast.walk(drzewo):
                if isinstance(w, ast.Name) and w.id == "t" and isinstance(w.ctx, ast.Store):
                    self.fail(f"{plik.name}:{w.lineno}: przypisanie do `t`")
                if isinstance(w, ast.arg) and w.arg == "t":
                    self.fail(f"{plik.name}:{w.lineno}: argument `t`")

    def test_nieznany_jezyk_po_angielsku(self):
        import teksty
        try:
            teksty.ustaw("de")
            self.assertEqual(teksty.t("kier_gorzej"), "↑ worse")
        finally:
            teksty.ustaw("pl")


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
