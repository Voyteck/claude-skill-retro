"""Wyciąga sygnały do retro z transkrypcji Claude Code, gita i GitHuba.

Użycie:
  python sygnaly.py --od 2026-10-06 [--do 2026-10-08] [--katalog KATALOG_ROBOCZY] [--wyjscie KATALOG]
                    [--projekt NAZWA ...] [--bez-gh]

--od/--do: daty lokalne, obie włącznie. Katalog roboczy: z --katalog albo wykryty (wspolne.znajdz_katalog_roboczy).
Wynik (domyślnie <katalog roboczy>/dane/sygnaly-<od>_<do>/):
  podsumowanie.md   liczby całościowe i per projekt, pory dnia, git/GitHub, pliki reguł, zmiany pamięci
  <projekt>.md      oś czasu: wiadomości właściciela, pytania i odpowiedzi, blokady, przerwania
  metryki.json      liczby do metryki.csv
Tryb „projekt” (konfiguracja) bierze tylko sesje i repo tego projektu. Transkrypcji nie modyfikuje.
"""
import argparse
import collections
import datetime as dt
import json
import pathlib
import re
import statistics
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wspolne  # noqa: E402

WZOR_KOREKTY = re.compile(
    r"(^|\W)(nie |dlaczego|czemu|znowu|ponownie|przecież|mówiłem|prosiłem|miałeś|miałaś|"
    r"zapomnia|źle|błąd|nie widzę|gdzie jest|stop\b|czekaj|zatrzymaj|jeszcze raz|"
    r"why\b|again\b|wrong\b|don't\b|didn't\b)",
    re.IGNORECASE,
)
# Rekomendacja bywa opisana różnie: „(rekomendowane)”, „(Rekomendacja)”, „— zalecam”, „(zalecane)”, „(Recommended)”.
WZOR_REKOMENDACJI = re.compile(r"(?<!nie )\b(rekomend\w*|recommended|zalec\w*)", re.IGNORECASE)
WZOR_PR = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/pull/\d+")


# ---------------------------------------------------------------- pomocnicze

def czas_lokalny(ts: str):
    try:
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
    except (ValueError, AttributeError):
        return None


class Projekty:
    """Mapuje katalog sesji na (nazwa projektu, katalog repo)."""

    def __init__(self, konf: dict):
        self.poprawki = [(p.lower(), n) for p, n in konf.get("nazwy_projektow") or []]
        self.cache = {}

    def __call__(self, cwd: str):
        if cwd in self.cache:
            return self.cache[cwd]
        c = (cwd or "").lower()
        wynik = None
        for podciag, nazwa in self.poprawki:
            if podciag in c:
                # poprawka zmienia tylko nazwę; repo nadal z gita, żeby liczyły się jego commity, PR-y i reguły
                wynik = (nazwa, wspolne.git_glowny_katalog(cwd) if cwd else None)
                break
        if wynik is None and "scratch-workspaces" in c:
            wynik = ("bez-folderu", None)
        if wynik is None and cwd:
            glowny = wspolne.git_glowny_katalog(cwd)
            wynik = (pathlib.Path(glowny).name, glowny) if glowny else (pathlib.PurePath(cwd).name or "nieznany", None)
        wynik = wynik or ("nieznany", None)
        self.cache[cwd] = wynik
        return wynik


def tekst_tresci(tresc) -> str:
    if isinstance(tresc, str):
        return tresc
    if isinstance(tresc, list):
        czesci = []
        for x in tresc:
            if x.get("type") == "text":
                czesci.append(x.get("text", ""))
            elif x.get("type") == "image":
                czesci.append("[obraz]")
            elif x.get("type") == "tool_result":
                t = x.get("content")
                czesci.append(t if isinstance(t, str) else json.dumps(t, ensure_ascii=False))
        return "\n".join(czesci)
    return ""


def skroc(t: str, n: int) -> str:
    t = re.sub(r"\s+", " ", t or "").strip()
    return t if len(t) <= n else t[: n - 1] + "…"


def parsuj_odpowiedzi(tekst: str, pytania: list) -> list:
    """Wyciąga odpowiedź na każde pytanie z wyniku AskUserQuestion."""
    wyniki = []
    for i, q in enumerate(pytania):
        znacznik = '"' + q.get("question", "") + '"="'
        p = tekst.find(znacznik)
        if p < 0:
            wyniki.append(None)
            continue
        start = p + len(znacznik)
        kon = None
        for q2 in pytania[i + 1:]:
            p2 = tekst.find(', "' + q2.get("question", "") + '"="', start)
            if p2 >= 0:
                kon = p2
                break
        if kon is None:
            for koniec in ('". Read the answers', '". You can now continue', '" user notes', '" selected'):
                p3 = tekst.find(koniec, start)
                if p3 >= 0:
                    kon = p3
                    break
        if kon is None:
            kon = tekst.rfind('"')
            kon = kon if kon >= start else len(tekst)
        wyniki.append(tekst[start:kon].rstrip('"'))
    return wyniki


def klasyfikuj_odpowiedz(odp, q) -> str:
    if odp is None:
        return "nieznana"
    if "[User dismissed" in odp:
        return "odlozone"
    if odp.strip() == "[No preference]":
        return "bez_wyboru"
    etykiety = [o.get("label", "") for o in q.get("options", [])]
    rekom = {e for e in etykiety if WZOR_REKOMENDACJI.search(e)}
    wybrane, reszta = [], odp
    for e in sorted(etykiety, key=len, reverse=True):
        if e and e in reszta:
            wybrane.append(e)
            reszta = reszta.replace(e, "", 1)
    if wybrane and not reszta.strip(" ,"):
        if not rekom:
            return "bez_rekomendacji"
        return "rekomendowana" if rekom & set(wybrane) else "inna"
    return "wlasna"


# ---------------------------------------------------------------- transkrypcje

class Sesja:
    def __init__(self, plik: pathlib.Path):
        self.sid = plik.stem
        self.folder = plik.parent
        self.tytul = ""
        self.cwd = collections.Counter()
        self.modele = collections.Counter()
        self.zdarzenia = []       # (czas, rodzaj, dane)
        self.licz = collections.Counter()
        self.bledy = collections.Counter()
        self.podagenci = collections.Counter()         # (typ, model z wywołania)
        self.podagenci_modele = collections.Counter()  # (typ, model faktyczny)
        self.pr = set()
        self.pierwszy = None
        self.ostatni = None
        self.projekt = ("nieznany", None)

    def przypisz_projekt(self, projekty: Projekty):
        nazwy = collections.Counter()
        korzenie = {}
        for c, n in self.cwd.items():
            nazwa, korzen = projekty(c)
            nazwy[nazwa] += n
            korzenie.setdefault(nazwa, korzen)
        nazwane = [(n, k) for k, n in nazwy.items() if k != "bez-folderu"]
        if nazwane:
            nazwa = max(nazwane)[1]
        else:
            nazwa = "bez-folderu" if nazwy else "nieznany"
        self.projekt = (nazwa, korzenie.get(nazwa))


def czytaj_sesje(plik: pathlib.Path, od: dt.datetime, do: dt.datetime) -> Sesja:
    s = Sesja(plik)
    narzedzia = {}           # tool_use_id -> (nazwa, input)
    ostatni_tekst_asystenta = ""
    with plik.open(encoding="utf-8", errors="replace") as f:
        for linia in f:
            try:
                d = json.loads(linia)
            except ValueError:
                continue
            typ = d.get("type")
            if typ == "custom-title":
                s.tytul = d.get("customTitle") or s.tytul
                continue
            if d.get("cwd"):
                s.cwd[d["cwd"]] += 1
            wiad = d.get("message") or {}
            tresc = wiad.get("content")
            if typ == "assistant" and isinstance(tresc, list):
                for x in tresc:
                    if x.get("type") == "tool_use":
                        narzedzia[x.get("id")] = (x.get("name"), x.get("input") or {})
            czas = czas_lokalny(d.get("timestamp", ""))
            if czas is None or not (od <= czas < do):
                if typ == "assistant" and isinstance(tresc, list):
                    t = " ".join(x.get("text", "") for x in tresc if x.get("type") == "text")
                    if t.strip():
                        ostatni_tekst_asystenta = t
                continue
            s.pierwszy = s.pierwszy or czas
            s.ostatni = czas

            if typ == "pr-link" or (typ not in ("user", "assistant") and "/pull/" in linia):
                s.pr.update(WZOR_PR.findall(linia))
            if typ == "system":
                if d.get("subtype") == "compact_boundary":
                    s.licz["kompakty"] += 1
                    s.zdarzenia.append((czas, "kompakt", {}))
                elif d.get("subtype") == "api_error":
                    s.licz["bledy_api"] += 1
                continue

            if typ == "assistant" and isinstance(tresc, list):
                if wiad.get("model"):
                    s.modele[wiad["model"]] += 1
                t = " ".join(x.get("text", "") for x in tresc if x.get("type") == "text")
                if t.strip():
                    ostatni_tekst_asystenta = t
                for x in tresc:
                    if x.get("type") != "tool_use":
                        continue
                    nazwa, wej = x.get("name"), x.get("input") or {}
                    if nazwa in ("Agent", "Task"):
                        s.licz["podagenci"] += 1
                        s.podagenci[(wej.get("subagent_type") or "general-purpose", wej.get("model") or "dziedziczony")] += 1
                    elif nazwa == "SendMessage":
                        s.licz["wiad_do_sesji"] += 1
                    elif nazwa == "Workflow":
                        s.licz["workflow"] += 1
                continue

            if typ != "user":
                continue
            pochodzenie = (d.get("origin") or {}).get("kind")
            if pochodzenie == "peer":
                s.licz["wiad_od_sesji"] += 1
                continue
            if d.get("isMeta") or d.get("isCompactSummary"):
                continue
            tekst = tekst_tresci(tresc)

            if isinstance(tresc, list) and any(x.get("type") == "tool_result" for x in tresc):
                for x in tresc:
                    if x.get("type") != "tool_result":
                        continue
                    nazwa, wej = narzedzia.get(x.get("tool_use_id"), ("?", {}))
                    wynik = tekst_tresci([x])
                    if nazwa == "AskUserQuestion":
                        pytania = wej.get("questions") or []
                        if "Tool call interrupted" in wynik or (x.get("is_error") and "answered" not in wynik):
                            s.licz["pytania_przerwane"] += len(pytania) or 1
                            continue
                        for q, odp in zip(pytania, parsuj_odpowiedzi(wynik, pytania)):
                            klasa = klasyfikuj_odpowiedz(odp, q)
                            s.licz["pytania"] += 1
                            s.licz["pyt_" + klasa] += 1
                            s.zdarzenia.append((czas, "pytanie", {
                                "pytanie": q.get("question", ""),
                                "opcje": [o.get("label", "") for o in q.get("options", [])],
                                "odpowiedz": odp, "klasa": klasa}))
                        continue
                    low = wynik[:400].lower()
                    if "denied by the claude code auto mode classifier" in low:
                        s.licz["blokady_klasyfikatora"] += 1
                        s.zdarzenia.append((czas, "blokada", {"narzedzie": nazwa, "wejscie": skroc(json.dumps(wej, ensure_ascii=False), 300)}))
                    elif "doesn't want to proceed" in low or "user rejected" in low or "user denied" in low:
                        s.licz["odmowy_wlasciciela"] += 1
                        s.zdarzenia.append((czas, "odmowa", {"narzedzie": nazwa, "wejscie": skroc(json.dumps(wej, ensure_ascii=False), 300)}))
                    elif x.get("is_error"):
                        s.licz["bledy_narzedzi"] += 1
                        klucz = re.sub(r"\d+", "#", skroc(wynik, 90))
                        s.bledy[(nazwa, klucz)] += 1
                continue

            if "Request interrupted by user" in tekst:
                s.licz["przerwania"] += 1
                s.zdarzenia.append((czas, "przerwanie", {"poprzedzone": skroc(ostatni_tekst_asystenta, 250)}))
                continue
            if tekst.lstrip().startswith("<command-name>"):
                m = re.search(r"<command-name>(.*?)</command-name>", tekst)
                s.licz["polecenia"] += 1
                s.zdarzenia.append((czas, "polecenie", {"polecenie": m.group(1) if m else "?"}))
                continue
            if tekst.lstrip().startswith(("<local-command", "<task-notification", "[Cross-session")):
                continue
            if pochodzenie in ("human", None) and tekst.strip():
                korekta = bool(WZOR_KOREKTY.search(tekst))
                s.licz["wiad_wlasciciela"] += 1
                s.licz["wiad_mozliwa_korekta"] += korekta
                s.zdarzenia.append((czas, "wlasciciel", {
                    "tekst": skroc(tekst, 1200), "korekta": korekta,
                    "poprzedzone": skroc(ostatni_tekst_asystenta, 250)}))

    # podagenci tej sesji: faktyczny typ i model z ich własnych transkrypcji
    katalog_pod = plik.with_suffix("") / "subagents"
    if katalog_pod.is_dir():
        for meta in katalog_pod.glob("agent-*.meta.json"):
            jsonl = meta.with_name(meta.name.replace(".meta.json", ".jsonl"))
            if not jsonl.exists():
                continue
            try:
                typ_ag = json.loads(meta.read_text(encoding="utf-8")).get("agentType", "?")
            except ValueError:
                typ_ag = "?"
            model, w_oknie = "?", False
            with jsonl.open(encoding="utf-8", errors="replace") as f:
                for linia in f:
                    try:
                        d = json.loads(linia)
                    except ValueError:
                        continue
                    czas = czas_lokalny(d.get("timestamp", ""))
                    if czas and od <= czas < do:
                        w_oknie = True
                    if d.get("type") == "assistant" and (d.get("message") or {}).get("model"):
                        model = d["message"]["model"]
                        if w_oknie:
                            break
                    if d.get("type") == "user" and "denied by the Claude Code auto mode classifier" in linia:
                        if czas and od <= czas < do:
                            s.licz["blokady_u_podagentow"] += 1
            if w_oknie:
                s.podagenci_modele[(typ_ag, model)] += 1
    return s


def wszystkie_sesje(od, do, projekty: Projekty):
    sesje = []
    for plik in sorted((wspolne.katalog_claude() / "projects").glob("*/*.jsonl")):
        try:
            if dt.datetime.fromtimestamp(plik.stat().st_mtime).astimezone() < od:
                continue
        except OSError:
            continue
        s = czytaj_sesje(plik, od, do)
        if s.pierwszy:
            s.przypisz_projekt(projekty)
            sesje.append(s)
    return sesje


# ---------------------------------------------------------------- git i GitHub

def uruchom(polecenie, cwd):
    try:
        r = subprocess.run(polecenie, cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
        return r.returncode, r.stdout, r.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, "", str(e)


def git_i_gh(repozytoria: dict, od_data, do_data, gh):
    wynik = {}
    for nazwa, sciezka in repozytoria.items():
        if not pathlib.Path(sciezka, ".git").exists():
            continue
        r = {"commity": 0, "commity_fix": 0, "reverty": 0, "zmiany_regul": 0,
             "pr_otwarte": 0, "pr_scalone": 0, "pr_h_do_scalenia": [], "pr_commity": [],
             "ci_wszystkie": 0, "ci_porazki": 0, "gh": "ok" if gh else "pominięty (brak gh albo --bez-gh)"}
        zakres = [f"--since={od_data.isoformat()} 00:00", f"--until={do_data.isoformat()} 23:59:59"]
        kod, out, _ = uruchom(["git", "log", "--all", "--no-merges", "--format=%H%x09%s", *zakres], sciezka)
        if kod == 0:
            linie = {l.split("\t", 1)[0]: l.split("\t", 1)[-1] for l in out.splitlines() if l}
            r["commity"] = len(linie)
            r["commity_fix"] = sum(1 for t in linie.values() if re.match(r"fix", t, re.I))
            r["reverty"] = sum(1 for t in linie.values() if t.lower().startswith("revert"))
        kod, out, _ = uruchom(["git", "log", "--all", "--format=%H", *zakres, "--",
                               "CLAUDE.md", "*/CLAUDE.md", ".claude/CLAUDE.md", "CLAUDE.local.md"], sciezka)
        if kod == 0:
            r["zmiany_regul"] = len(set(out.split()))
        kod, out, _ = uruchom(["git", "remote"], sciezka)
        if not out.strip():
            r["gh"] = "brak zdalnego"
        elif gh:
            kod, out, err = uruchom([gh, "pr", "list", "--state", "all", "--limit", "300",
                                     "--json", "number,createdAt,mergedAt"], sciezka)
            if kod == 0:
                for pr in json.loads(out or "[]"):
                    utw = czas_lokalny(pr.get("createdAt") or "")
                    scal = czas_lokalny(pr.get("mergedAt") or "")
                    if utw and od_data <= utw.date() <= do_data:
                        r["pr_otwarte"] += 1
                    if scal and od_data <= scal.date() <= do_data:
                        r["pr_scalone"] += 1
                        if utw:
                            r["pr_h_do_scalenia"].append(round((scal - utw).total_seconds() / 3600, 1))
            else:
                r["gh"] = "błąd: " + skroc(err, 120)
            # Commity na PR (przybliżenie rund poprawek). GraphQL liczy węzły autorów: limit 40 mieści się w 500 tys.
            kod, out, err = uruchom([gh, "pr", "list", "--state", "merged", "--limit", "40",
                                     "--search", f"merged:{od_data.isoformat()}..{do_data.isoformat()}",
                                     "--json", "number,commits"], sciezka)
            if kod == 0:
                lista = json.loads(out or "[]")
                r["pr_commity"] = [len(pr.get("commits") or []) for pr in lista]
                if len(lista) == 40:
                    r["gh"] = "ok (commity/PR z 40 najnowszych)"
            kod, out, err = uruchom([gh, "run", "list", "--limit", "500",
                                     "--json", "conclusion,createdAt"], sciezka)
            if kod == 0:
                for run in json.loads(out or "[]"):
                    c = czas_lokalny(run.get("createdAt") or "")
                    if c and od_data <= c.date() <= do_data and run.get("conclusion"):
                        r["ci_wszystkie"] += 1
                        r["ci_porazki"] += run["conclusion"] in ("failure", "timed_out", "startup_failure")
        wynik[nazwa] = r
    return wynik


def pliki_regul(repozytoria: dict, konf: dict) -> list:
    pliki = [("globalne", wspolne.katalog_claude() / "CLAUDE.md")]
    for nazwa, sciezka in repozytoria.items():
        baza = pathlib.Path(sciezka)
        for wzor in ("CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md", "*/CLAUDE.md"):
            pliki += [(nazwa, p) for p in sorted(baza.glob(wzor))]
    pliki += [("dodatkowe", pathlib.Path(p).expanduser()) for p in konf.get("pliki_regul_dodatkowe") or []]
    wynik, widziane = [], set()
    for nazwa, p in pliki:
        try:
            klucz = str(p.resolve()).lower()
            if klucz in widziane or not p.is_file():
                continue
            widziane.add(klucz)
            wynik.append((nazwa, str(p), len(p.read_text(encoding="utf-8", errors="replace").splitlines())))
        except OSError:
            pass
    return wynik


def pamiec(foldery, od, projekty_folderow: dict):
    """Pliki pamięci w folderach transkrypcji; zmienione w oknie."""
    liczba, zmiany = 0, []
    for folder in foldery:
        for p in (folder / "memory").glob("*.md"):
            if p.name == "MEMORY.md":
                continue
            liczba += 1
            zm = dt.datetime.fromtimestamp(p.stat().st_mtime).astimezone()
            if zm >= od:
                zmiany.append((projekty_folderow.get(folder, folder.name[-40:]), p.name, zm))
    return liczba, sorted(zmiany, key=lambda x: x[2])


# ---------------------------------------------------------------- raporty

def pora(czas: dt.datetime, konf: dict) -> str:
    g = konf.get("godziny_pracy") or wspolne.DOMYSLNA_KONFIGURACJA["godziny_pracy"]
    minuty = lambda hhmm: int(hhmm[:2]) * 60 + int(hhmm[3:5])  # noqa: E731
    m = czas.hour * 60 + czas.minute
    if m < minuty(g["od"]):
        return f"noc (przed {g['od']})"
    if m < minuty(g["do"]):
        return f"dzień ({g['od']}–{g['do']})"
    if m < minuty(g["wieczor_do"]):
        return f"wieczór ({g['do']}–{g['wieczor_do']})"
    return f"noc (po {g['wieczor_do']})"


def raport_projektu(nazwa, sesje, od_data, do_data) -> str:
    l = [f"# {nazwa}: sygnały {od_data} … {do_data}", ""]
    l += ["## Sesje", "",
          "| sesja | tytuł | aktywna | wiad. wł. | pytania (rek/inna/własna/odł.) | przerw. | blokady | błędy | kompakty | podagenci |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for s in sesje:
        c = s.licz
        l.append(f"| `{s.sid[:8]}` | {s.tytul or '—'} | {s.pierwszy:%m-%d %H:%M} – {s.ostatni:%m-%d %H:%M} | "
                 f"{c['wiad_wlasciciela']} | {c['pytania']} ({c['pyt_rekomendowana']}/{c['pyt_inna']}/{c['pyt_wlasna']}/{c['pyt_odlozone']}) | "
                 f"{c['przerwania']} | {c['blokady_klasyfikatora']} | {c['bledy_narzedzi']} | {c['kompakty']} | {c['podagenci']} |")
    l += ["", "## Oś czasu", "",
          "Legenda: **[K?]** = heurystycznie możliwa korekta; klasy odpowiedzi: rekomendowana / inna / własna "
          "(tekst spoza opcji) / odłożone / bez wyboru.", ""]
    zdarzenia = sorted(((czas, s, r, d) for s in sesje for czas, r, d in s.zdarzenia), key=lambda x: x[0])
    for czas, s, rodzaj, d in zdarzenia:
        znak = f"`{czas:%m-%d %H:%M}` `{s.sid[:8]}`"
        if rodzaj == "wlasciciel":
            l.append(f"- {znak} **Właściciel{' [K?]' if d['korekta'] else ''}:** {d['tekst']}")
            if d["poprzedzone"]:
                l.append(f"  - ↳ wcześniej Claude: _{d['poprzedzone']}_")
        elif rodzaj == "pytanie":
            l.append(f"- {znak} **Pytanie:** {skroc(d['pytanie'], 300)} → **{d['klasa']}:** {skroc(d['odpowiedz'] or '', 500)}")
        elif rodzaj == "blokada":
            l.append(f"- {znak} **Blokada klasyfikatora** ({d['narzedzie']}): `{d['wejscie']}`")
        elif rodzaj == "odmowa":
            l.append(f"- {znak} **Odmowa właściciela** ({d['narzedzie']}): `{d['wejscie']}`")
        elif rodzaj == "przerwanie":
            l.append(f"- {znak} **Przerwanie przez właściciela.** Wcześniej Claude: _{d['poprzedzone']}_")
        elif rodzaj == "polecenie":
            l.append(f"- {znak} Polecenie `{d['polecenie']}`")
        elif rodzaj == "kompakt":
            l.append(f"- {znak} Kompakt kontekstu")
    bledy = collections.Counter()
    for s in sesje:
        bledy.update(s.bledy)
    if bledy:
        l += ["", "## Najczęstsze błędy narzędzi", ""]
        for (narz, kom), n in bledy.most_common(15):
            l.append(f"- {n}× **{narz}**: {kom}")
    pod, pod_m = collections.Counter(), collections.Counter()
    for s in sesje:
        pod.update(s.podagenci)
        pod_m.update(s.podagenci_modele)
    if pod or pod_m:
        l += ["", "## Podagenci", "", "Wywołania (typ, model zadany w wywołaniu):", ""]
        for (t, m), n in pod.most_common():
            l.append(f"- {n}× {t} / {m}")
        l += ["", "Faktycznie uruchomieni (typ, model z ich transkrypcji):", ""]
        for (t, m), n in pod_m.most_common():
            l.append(f"- {n}× {t} / {m}")
    pr = sorted(set().union(*(s.pr for s in sesje)))
    if pr:
        l += ["", "## PR-y wspomniane w sesjach", ""] + [f"- {u}" for u in pr]
    return "\n".join(l) + "\n"


def nazwa_pliku(nazwa: str) -> str:
    return re.sub(r"[^\w.-]+", "-", nazwa).strip("-") or "projekt"


def main(argv=None):
    for strumien in (sys.stdout, sys.stderr):
        try:
            strumien.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--od", required=True, help="pierwszy dzień okna (RRRR-MM-DD, lokalnie, włącznie)")
    ap.add_argument("--do", help="ostatni dzień okna (włącznie); domyślnie dziś")
    ap.add_argument("--katalog", help="katalog roboczy retro; domyślnie wykryty")
    ap.add_argument("--wyjscie", help="katalog wyniku; domyślnie <katalog roboczy>/dane/sygnaly-<od>_<do>")
    ap.add_argument("--projekt", action="append", help="tylko te projekty (można powtórzyć)")
    ap.add_argument("--bez-gh", action="store_true", help="nie pytaj GitHuba (PR-y, CI)")
    a = ap.parse_args(argv)

    if a.katalog:
        katalog, tryb = pathlib.Path(a.katalog).expanduser(), None
    else:
        katalog, tryb = wspolne.znajdz_katalog_roboczy()
    if katalog is None and not a.wyjscie:
        sys.exit("Nie znaleziono katalogu roboczego retro. Załóż go: python zaloz.py --tryb konto|projekt (patrz SKILL.md).")
    konf = wspolne.wczytaj_konfiguracje(katalog)

    od_data = dt.date.fromisoformat(a.od)
    do_data = dt.date.fromisoformat(a.do) if a.do else dt.date.today()
    od = dt.datetime.combine(od_data, dt.time()).astimezone()
    do = dt.datetime.combine(do_data + dt.timedelta(days=1), dt.time()).astimezone()
    wyjscie = pathlib.Path(a.wyjscie) if a.wyjscie else katalog / "dane" / f"sygnaly-{od_data}_{do_data}"
    wyjscie.mkdir(parents=True, exist_ok=True)

    projekty = Projekty(konf)
    sesje = wszystkie_sesje(od, do, projekty)

    # zakres: tryb projektu = tylko repo, w którym leży .retro; --projekt zawęża; pomin_projekty wyklucza
    repo_projektu = None
    if konf.get("tryb") == "projekt" and katalog is not None:
        repo_projektu = wspolne.git_glowny_katalog(str(katalog.parent)) or str(katalog.parent)
    wybrane = set(a.projekt or [])
    pomin = set(konf.get("pomin_projekty") or [])

    def w_zakresie(s):
        nazwa, korzen = s.projekt
        if nazwa in pomin or (wybrane and nazwa not in wybrane):
            return False
        if repo_projektu:
            return bool(korzen) and pathlib.Path(korzen).resolve() == pathlib.Path(repo_projektu).resolve()
        return True

    sesje = [s for s in sesje if w_zakresie(s)]
    per_projekt = collections.defaultdict(list)
    for s in sesje:
        per_projekt[s.projekt[0]].append(s)
    for nazwa, lista in per_projekt.items():
        lista.sort(key=lambda s: s.pierwszy)
        (wyjscie / f"{nazwa_pliku(nazwa)}.md").write_text(raport_projektu(nazwa, lista, od_data, do_data), encoding="utf-8")

    # repozytoria: wykryte z sesji w zakresie + dodatkowe z konfiguracji
    repozytoria = {}
    if repo_projektu:
        repozytoria[pathlib.Path(repo_projektu).name] = repo_projektu
    else:
        for s in sesje:
            nazwa, korzen = s.projekt
            if korzen and pathlib.Path(korzen).is_dir():
                repozytoria.setdefault(nazwa, korzen)
        for nazwa, sciezka in (konf.get("repozytoria_dodatkowe") or {}).items():
            if nazwa not in pomin and (not wybrane or nazwa in wybrane):
                repozytoria.setdefault(nazwa, str(pathlib.Path(sciezka).expanduser()))
    gh = None if a.bez_gh else wspolne.sciezka_gh(konf)
    repo = git_i_gh(repozytoria, od_data, do_data, gh)
    regul = pliki_regul(repozytoria, konf)
    projekty_folderow = {}
    for s in sesje:
        projekty_folderow.setdefault(s.folder, s.projekt[0])
    if repo_projektu or wybrane:
        foldery = sorted(projekty_folderow)
    else:
        foldery = sorted(p for p in (wspolne.katalog_claude() / "projects").glob("*") if p.is_dir())
    pamiec_liczba, pamiec_zmiany = pamiec(foldery, od, projekty_folderow)

    suma = collections.Counter()
    for s in sesje:
        suma.update(s.licz)
    pory = collections.Counter(pora(czas, konf) for s in sesje for czas, r, _ in s.zdarzenia if r == "wlasciciel")
    h_scal = [h for r in repo.values() for h in r["pr_h_do_scalenia"]]
    c_pr = [c for r in repo.values() for c in r["pr_commity"]]
    metryki = {
        "okno_od": od_data.isoformat(), "okno_do": do_data.isoformat(),
        "dni_robocze": wspolne.dni_robocze_po(od_data - dt.timedelta(days=1), do_data, konf),
        "sesje": len(sesje), "projekty": len(per_projekt),
        "wiad_wlasciciela": suma["wiad_wlasciciela"], "wiad_mozliwa_korekta": suma["wiad_mozliwa_korekta"],
        "wiad_po_20": sum(n for k, n in pory.items() if k.startswith("noc")),
        "pytania": suma["pytania"], "pyt_rekomendowana": suma["pyt_rekomendowana"], "pyt_inna": suma["pyt_inna"],
        "pyt_wlasna": suma["pyt_wlasna"], "pyt_odlozone": suma["pyt_odlozone"],
        "pyt_bez_rekomendacji": suma["pyt_bez_rekomendacji"], "pyt_bez_wyboru": suma["pyt_bez_wyboru"],
        "przerwania": suma["przerwania"], "blokady_klasyfikatora": suma["blokady_klasyfikatora"] + suma["blokady_u_podagentow"],
        "odmowy_wlasciciela": suma["odmowy_wlasciciela"], "bledy_narzedzi": suma["bledy_narzedzi"],
        "kompakty": suma["kompakty"], "podagenci": suma["podagenci"], "wiad_miedzy_sesjami": suma["wiad_do_sesji"],
        "commity": sum(r["commity"] for r in repo.values()),
        "pr_otwarte": sum(r["pr_otwarte"] for r in repo.values()), "pr_scalone": sum(r["pr_scalone"] for r in repo.values()),
        "pr_mediana_h": round(statistics.median(h_scal), 1) if h_scal else None,
        "pr_mediana_commitow": statistics.median(c_pr) if c_pr else None,
        "ci_wszystkie": sum(r["ci_wszystkie"] for r in repo.values()), "ci_porazki": sum(r["ci_porazki"] for r in repo.values()),
        "claude_md_linie": sum(n for _, _, n in regul), "pamiec_pliki": pamiec_liczba,
    }
    (wyjscie / "metryki.json").write_text(json.dumps(metryki, ensure_ascii=False, indent=2), encoding="utf-8")

    zakres = f"projekt `{repo_projektu}`" if repo_projektu else "całe konto (wszystkie projekty z transkrypcji)"
    if wybrane:
        zakres += f", zawężone do: {', '.join(sorted(wybrane))}"
    l = [f"# Sygnały do retro: {od_data} … {do_data}", "",
         f"Wygenerowano {dt.datetime.now():%Y-%m-%d %H:%M} skryptem `scripts/sygnaly.py` skillu retro. Zakres: {zakres}. "
         "Liczby z heurystyk (np. „możliwa korekta”) są wskazówką, nie dowodem: dowodem jest wpis w osi czasu projektu.", "",
         "## Metryki", "", "| metryka | wartość |", "|---|---|"]
    l += [f"| {k} | {v} |" for k, v in metryki.items()]
    l += ["", "## Projekty", "", "| projekt | sesje | wiad. wł. | [K?] | pytania | rek. | inna | własna | odłożone | przerw. | blokady | błędy | kompakty | podagenci |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for nazwa, lista in sorted(per_projekt.items()):
        c = collections.Counter()
        for s in lista:
            c.update(s.licz)
        l.append(f"| [{nazwa}]({nazwa_pliku(nazwa)}.md) | {len(lista)} | {c['wiad_wlasciciela']} | {c['wiad_mozliwa_korekta']} | {c['pytania']} | "
                 f"{c['pyt_rekomendowana']} | {c['pyt_inna']} | {c['pyt_wlasna']} | {c['pyt_odlozone']} | {c['przerwania']} | "
                 f"{c['blokady_klasyfikatora'] + c['blokady_u_podagentow']} | {c['bledy_narzedzi']} | {c['kompakty']} | {c['podagenci']} |")
    l += ["", "## Pora wiadomości właściciela", ""] + [f"- {k}: {v}" for k, v in sorted(pory.items())]
    l += ["", "## Repozytoria", "", "| repo | ścieżka | commity | fix | revert | zmiany reguł | PR otw. | PR scal. | mediana h do scalenia | mediana commitów/PR | CI porażki/wszystkie | gh |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for nazwa, r in repo.items():
        med_h = statistics.median(r["pr_h_do_scalenia"]) if r["pr_h_do_scalenia"] else "—"
        med_c = statistics.median(r["pr_commity"]) if r["pr_commity"] else "—"
        l.append(f"| {nazwa} | `{repozytoria[nazwa]}` | {r['commity']} | {r['commity_fix']} | {r['reverty']} | {r['zmiany_regul']} | {r['pr_otwarte']} | "
                 f"{r['pr_scalone']} | {med_h} | {med_c} | {r['ci_porazki']}/{r['ci_wszystkie']} | {r['gh']} |")
    l += ["", "## Pliki reguł (linie)", ""] + [f"- {n} `{p}`: {k}" for n, p, k in regul]
    l += ["", f"## Pamięć: {pamiec_liczba} plików, zmienione w oknie: {len(pamiec_zmiany)}", ""]
    l += [f"- `{zm:%m-%d %H:%M}` {proj} / {nazwa}" for proj, nazwa, zm in pamiec_zmiany]
    (wyjscie / "podsumowanie.md").write_text("\n".join(l) + "\n", encoding="utf-8")
    print(f"OK: {len(sesje)} sesji, {len(per_projekt)} projektów, {len(repo)} repo -> {wyjscie}")
    return metryki


if __name__ == "__main__":
    main()
