"""Wyciąga sygnały do retro z transkrypcji Claude Code, gita i GitHuba.

Użycie:
  python sygnaly.py --od 2026-10-06 [--do 2026-10-08] [--katalog KATALOG_ROBOCZY] [--wyjscie KATALOG]
                    [--projekt NAZWA ...] [--bez-gh] [--od-poczatku-dnia]

--od/--do: daty lokalne, obie włącznie; --od może mieć godzinę (2026-10-06T18:08). Gdy --od to sama data, a tego dnia
zakończono retro (commit ze „**Status:** zakończone” w katalogu roboczym), okno zaczyna się od godziny tego commita;
--od-poczatku-dnia to wyłącza. Katalog roboczy: z --katalog albo wykryty (wspolne.znajdz_katalog_roboczy).
Wynik (domyślnie <katalog roboczy>/dane/sygnaly-<od>_<do>/):
  podsumowanie.md   liczby całościowe i per projekt, pory dnia, tokeny i koszt, git/GitHub, pliki reguł, pamięć
  <projekt>.md      oś czasu: wiadomości właściciela, pytania i odpowiedzi, blokady, przerwania
  metryki.json      liczby do metryki.csv
Tryb „projekt” (konfiguracja) bierze tylko sesje i repo tego projektu. Transkrypcji nie modyfikuje.
"""
import argparse
import bisect
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
# Sesje uruchomione w scratchpadzie Claude Code (np. `claude -p` z testów) to nie praca właściciela.
WZOR_SCRATCHPAD = re.compile(r"[\\/]claude(-\d+)?[\\/].+[\\/]scratchpad([\\/]|$)", re.IGNORECASE)

# Sekrety w raportach. Raporty trafiają do `dane/` i do kontekstu podagentów, więc ciągi wyglądające na sekret
# są zamazywane przed zapisem. Heurystyka: wzór (zachowany przedrostek, sekret) albo cały dopasowany ciąg.
ZAMAZANE = "[zamazane]"
_WARTOSC = r"(\\\"[^\"]*?\\\"|\"[^\"]*\"|'[^']*'|[^\s\"'`,;|)]+)"
WZORY_SEKRETOW = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S), False),
    (re.compile(r"(gh\s+(?:secret|variable)\s+set\b[^\n|;&]*?(?:--body(?:=|\s+)|\s-b\s+))" + _WARTOSC), True),
    (re.compile(r"(?i)\b([\w.-]*(?:key|token|secret|pass|pwd|has[lł]o|klucz)[\w.-]*\s*[=:]\s*)"
                r"(?=[\\\"']*[^\s\"'`,;|)]*\d)(?=[\\\"']*[^\s\"'`,;|)]*[A-Za-z])"
                r"(\\\"[^\"]{8,}?\\\"|\"[^\"]{8,}\"|'[^']{8,}'|[^\s\"'`,;|)]{8,})"), True),
    (re.compile(r"(?i)\b(bearer\s+)([A-Za-z0-9._~+/=-]{16,})"), True),
    (re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}"
                r"|AIza[0-9A-Za-z_-]{30,}|xox[abprs]-[A-Za-z0-9-]{10,}|hf_[A-Za-z0-9]{20,}"
                r"|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})"), False),
]
WZOR_DLUGI_CIAG = re.compile(r"(?<![A-Za-z0-9+=])[A-Za-z0-9+=]{32,}(?![A-Za-z0-9+=])")
WZOR_HEX = re.compile(r"[0-9a-fA-F]+\Z")
# Pytanie o fakt znany tylko użytkownikowi (np. „gdzie jestem?”) nie ma opcji rekomendowanej z natury.
ZNACZNIK_FAKTU = "[fakt]"

# Tokeny. Wybudzenie = wywołanie sesji głównej, które po przerwie zapisuje od nowa duży cache.
PROG_WYBUDZENIA_TOKENY = 50_000
PROG_WYBUDZENIA_H = 1
PROG_DUZEGO_KONTEKSTU = 200_000
PLIK_CENNIKA = pathlib.Path(__file__).resolve().parent.parent / "references" / "cennik.json"
# Commit lub PR „bez lokalnej sesji”: brak zapisu w transkrypcjach tego repo w tym odstępie.
MARGINES_SESJI_MIN = 30


# ---------------------------------------------------------------- pomocnicze

def zamaz(tekst: str):
    """Zwraca (tekst z zamazanymi sekretami, liczba zamazań)."""
    licznik = 0

    def z_przedrostkiem(m):
        nonlocal licznik
        licznik += 1
        return m.group(1) + ZAMAZANE

    def caly(m):
        nonlocal licznik
        licznik += 1
        return ZAMAZANE

    def dlugi(m):
        nonlocal licznik
        ciag = m.group(0)
        if not (re.search(r"\d", ciag) and re.search(r"[A-Za-z]", ciag)):
            return ciag
        if WZOR_HEX.match(ciag) and len(ciag) == 40:        # hash commitu to dowód, nie sekret
            return ciag
        if m.string[max(0, m.start() - 7):m.start()].lower() == "sha256:":   # digest obrazu
            return ciag
        licznik += 1
        return ZAMAZANE

    for wzor, z_grupa in WZORY_SEKRETOW:
        tekst = wzor.sub(z_przedrostkiem if z_grupa else caly, tekst)
    tekst = WZOR_DLUGI_CIAG.sub(dlugi, tekst)
    return tekst, licznik



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
    if ZNACZNIK_FAKTU in (q.get("question") or "").lower():
        # odpowiedź na pytanie o fakt bywa tekstem spoza opcji, ale to nie korekta kierunku
        return "fakt"
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


# ---------------------------------------------------------------- cennik

def wczytaj_cennik(konf: dict) -> dict:
    """Cennik z references/cennik.json; pole `cennik` konfiguracji nadpisuje lub dodaje modele i stałe."""
    try:
        cennik = json.loads(PLIK_CENNIKA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cennik = {"modele": {}}
    wlasny = konf.get("cennik") or {}
    modele = dict(cennik.get("modele") or {})
    modele.update(wlasny.get("modele") or {})
    cennik.update({k: v for k, v in wlasny.items() if k != "modele"})
    cennik["modele"] = modele
    return cennik


def stawki(model: str, cennik: dict):
    """Stawki modelu po najdłuższym pasującym przedrostku identyfikatora albo None."""
    model = (model or "").replace("[1m]", "")
    pasujace = [k for k in cennik.get("modele", {}) if model.startswith(k)]
    return cennik["modele"][max(pasujace, key=len)] if pasujace else None


def koszt_wywolania(w: dict, cennik: dict, tylko_zapis=False):
    """Koszt wywołania w USD (None, gdy modelu nie ma w cenniku); tylko_zapis = sama część zapisu cache."""
    s = stawki(w["model"], cennik)
    if s is None:
        return None
    mnoznik = 1.0
    prog = s.get("powyzej") or {}
    if prog and w["kontekst"] > prog.get("kontekst", float("inf")):
        mnoznik = prog.get("mnoznik", 1)
    if w["fast"]:
        mnoznik *= cennik.get("mnoznik_fast", 1)
    zapis = w["zapis_5m"] * s.get("zapis_5m", 0) + w["zapis_1h"] * s.get("zapis_1h", 0)
    if tylko_zapis:
        return zapis * mnoznik / 1e6
    tokeny = w["wejscie"] * s.get("wejscie", 0) + w["wyjscie"] * s.get("wyjscie", 0) + zapis + w["odczyt"] * s.get("odczyt", 0)
    return tokeny * mnoznik / 1e6 + w["web_search"] * cennik.get("web_search_za_zapytanie", 0)


def wywolanie_api(d: dict, czas, podagent: bool):
    """Rekord asystenta z `usage` i `message.id` → (id, wywołanie) albo None."""
    wiad = d.get("message") or {}
    u = wiad.get("usage")
    if not isinstance(u, dict) or not wiad.get("id") or not wiad.get("model") or wiad["model"] == "<synthetic>":
        return None
    zapis = u.get("cache_creation_input_tokens") or 0
    rozbicie = u.get("cache_creation") or {}
    zapis_1h = rozbicie.get("ephemeral_1h_input_tokens") or 0
    w = {"czas": czas, "podagent": podagent, "model": wiad["model"],
         "wejscie": u.get("input_tokens") or 0, "wyjscie": u.get("output_tokens") or 0,
         "zapis_5m": zapis - zapis_1h, "zapis_1h": zapis_1h, "odczyt": u.get("cache_read_input_tokens") or 0,
         "fast": u.get("speed") == "fast", "web_search": (u.get("server_tool_use") or {}).get("web_search_requests") or 0}
    w["kontekst"] = w["wejscie"] + zapis + w["odczyt"]
    return wiad["id"], w


def dodaj_wywolanie(wywolania: dict, wynik):
    """Ten sam message.id jest zapisany raz na blok treści, z częściowym `usage` w trakcie strumienia:
    zostaje rekord z największym `output_tokens` i najwcześniejszym czasem."""
    if wynik is None:
        return
    mid, w = wynik
    stary = wywolania.get(mid)
    if stary is None:
        wywolania[mid] = w
    elif w["wyjscie"] >= stary["wyjscie"]:
        w["czas"] = min(w["czas"], stary["czas"])
        wywolania[mid] = w
    else:
        stary["czas"] = min(w["czas"], stary["czas"])


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
        self.start = None          # najwcześniejszy rekord pliku, także sprzed okna
        self.czasy = []            # czasy rekordów w oknie (sesja i podagenci): aktywność przy commitach
        self.wywolania = {}        # message.id -> wywołanie API (sesja i podagenci, także spoza okna)
        self.koszt = None          # koszt w oknie po deduplikacji (metryki_tokenow)
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
    ostatnie_wlasciciela = {}  # tekst -> (czas, w_trakcie); ta sama wiadomość bywa i w kolejce, i jako zwykła

    def wiadomosc_wlasciciela(tekst, czas, w_trakcie=False):
        klucz = tekst.strip()
        poprzednio = ostatnie_wlasciciela.get(klucz)
        ostatnie_wlasciciela[klucz] = (czas, w_trakcie)
        if poprzednio and poprzednio[1] != w_trakcie and abs((czas - poprzednio[0]).total_seconds()) < 120:
            return
        korekta = bool(WZOR_KOREKTY.search(tekst))
        s.licz["wiad_wlasciciela"] += 1
        s.licz["wiad_mozliwa_korekta"] += korekta
        s.licz["wiad_w_trakcie"] += w_trakcie
        s.zdarzenia.append((czas, "wlasciciel", {
            "tekst": skroc(tekst, 1200), "korekta": korekta, "w_trakcie": w_trakcie,
            "poprzedzone": skroc(ostatni_tekst_asystenta, 250)}))

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
            if czas is not None:
                s.start = min(s.start, czas) if s.start else czas
                if typ == "assistant":
                    dodaj_wywolanie(s.wywolania, wywolanie_api(d, czas, False))
            if czas is None or not (od <= czas < do):
                if typ == "assistant" and isinstance(tresc, list):
                    t = " ".join(x.get("text", "") for x in tresc if x.get("type") == "text")
                    if t.strip():
                        ostatni_tekst_asystenta = t
                continue
            s.pierwszy = s.pierwszy or czas
            s.ostatni = czas
            s.czasy.append(czas)

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

            if typ == "attachment":
                # Wiadomość wysłana w trakcie pracy Claude'a: wchłonięta w turę, bez własnego rekordu „user”.
                zal = d.get("attachment") or {}
                if (zal.get("type") == "queued_command" and (zal.get("origin") or {}).get("kind") == "human"
                        and isinstance(zal.get("prompt"), str) and zal["prompt"].strip()):
                    wiadomosc_wlasciciela(zal["prompt"], czas, w_trakcie=True)
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
                wiadomosc_wlasciciela(tekst, czas)

    # podagenci tej sesji: faktyczny typ i model z ich własnych transkrypcji
    katalog_pod = plik.with_suffix("") / "subagents"
    if katalog_pod.is_dir():
        for jsonl in sorted(katalog_pod.glob("agent-*.jsonl")):
            try:
                typ_ag = json.loads(jsonl.with_suffix(".meta.json").read_text(encoding="utf-8")).get("agentType", "?")
            except (OSError, ValueError, AttributeError):
                typ_ag = "?"
            model, w_oknie, model_w_oknie = "?", False, False
            with jsonl.open(encoding="utf-8", errors="replace") as f:
                for linia in f:
                    try:
                        d = json.loads(linia)
                    except ValueError:
                        continue
                    czas = czas_lokalny(d.get("timestamp", ""))
                    if czas and od <= czas < do:
                        w_oknie = True
                        s.czasy.append(czas)
                    if d.get("type") == "assistant" and (d.get("message") or {}).get("model"):
                        if not model_w_oknie:
                            model = d["message"]["model"]
                            model_w_oknie = w_oknie
                        if czas:
                            dodaj_wywolanie(s.wywolania, wywolanie_api(d, czas, True))
                    if d.get("type") == "user" and "denied by the Claude Code auto mode classifier" in linia:
                        if czas and od <= czas < do:
                            s.licz["blokady_u_podagentow"] += 1
            if w_oknie:
                s.podagenci_modele[(typ_ag, model)] += 1
    return s


def katalogi_transkrypcji(konf: dict) -> list:
    """`<katalog Claude Code>/projects` i `transkrypcje_dodatkowe` z konfiguracji (kopie z innych maszyn):
    katalog `projects` albo katalog, który go zawiera."""
    katalogi = [wspolne.katalog_claude() / "projects"]
    for p in konf.get("transkrypcje_dodatkowe") or []:
        p = pathlib.Path(p).expanduser()
        katalogi.append(p / "projects" if (p / "projects").is_dir() else p)
    return katalogi


def wszystkie_sesje(od, do, projekty: Projekty, konf: dict = None):
    """Zwraca (sesje w oknie, liczba pominiętych sesji uruchomionych w scratchpadzie)."""
    sesje, w_scratchpadzie = [], 0
    pliki = sorted(p for k in katalogi_transkrypcji(konf or {}) for p in k.glob("*/*.jsonl"))
    for plik in pliki:
        try:
            if dt.datetime.fromtimestamp(plik.stat().st_mtime).astimezone() < od:
                continue
        except OSError:
            continue
        s = czytaj_sesje(plik, od, do)
        if not s.pierwszy:
            continue
        if s.cwd and all(WZOR_SCRATCHPAD.search(c) for c in s.cwd):
            w_scratchpadzie += 1
            continue
        s.przypisz_projekt(projekty)
        sesje.append(s)
    return sesje, w_scratchpadzie


def mediana(wartosci):
    return statistics.median(wartosci) if wartosci else None


def procent(czesc, calosc):
    return round(100 * czesc / calosc, 1) if calosc else None


def metryki_tokenow(sesje: list, od, do, cennik: dict) -> dict:
    """Tokeny i koszt w oknie. Wywołanie API = unikalny message.id w całym zbiorze sesji (kopia w innej
    sesji, np. po rozwidleniu, liczy się raz, w sesji, która zaczęła się wcześniej)."""
    widziane = set()
    w_oknie, glowne, startowe, wybudzenia, nieznane = [], [], [], [], collections.Counter()
    for s in sorted(sesje, key=lambda s: (s.start or s.pierwszy, s.sid)):
        wlasne, kopie = [], 0
        for mid, w in s.wywolania.items():
            if mid in widziane:
                kopie += 1
                continue
            widziane.add(mid)
            w = dict(w, sesja=s)
            w["koszt"] = koszt_wywolania(w, cennik)
            if w["koszt"] is None:
                nieznane[w["model"]] += od <= w["czas"] < do
            wlasne.append(w)
        s.koszt = sum(w["koszt"] or 0 for w in wlasne if od <= w["czas"] < do)
        w_oknie += [w for w in wlasne if od <= w["czas"] < do]
        glowna = sorted((w for w in wlasne if not w["podagent"]), key=lambda w: w["czas"])
        glowne += [w for w in glowna if od <= w["czas"] < do]
        if glowna and not kopie and od <= glowna[0]["czas"] < do:
            startowe.append(glowna[0]["kontekst"])
        for a, b in zip(glowna, glowna[1:]):
            przerwa_h = (b["czas"] - a["czas"]).total_seconds() / 3600
            if (od <= b["czas"] < do and przerwa_h > PROG_WYBUDZENIA_H
                    and b["zapis_5m"] + b["zapis_1h"] > PROG_WYBUDZENIA_TOKENY):
                wybudzenia.append({"sesja": s, "czas": b["czas"], "przerwa_h": przerwa_h,
                                   "zapis": b["zapis_5m"] + b["zapis_1h"],
                                   "koszt": koszt_wywolania(b, cennik, tylko_zapis=True) or 0})
    koszt = sum(w["koszt"] or 0 for w in w_oknie)
    koszt_pod = sum(w["koszt"] or 0 for w in w_oknie if w["podagent"])
    koszt_pod_opus = sum(w["koszt"] or 0 for w in w_oknie if w["podagent"] and "opus" in w["model"])
    wejscie = sum(w["kontekst"] for w in w_oknie)
    konteksty = [w["kontekst"] for w in glowne]
    m_start = mediana(startowe)
    return {
        "metryki": {
            "wywolania_api": len(w_oknie),
            "koszt_api_usd": round(koszt, 2),
            "kontekst_mediana": round(mediana(konteksty)) if konteksty else None,
            "kontekst_ponad_200k_proc": procent(sum(k > PROG_DUZEGO_KONTEKSTU for k in konteksty), len(konteksty)),
            "podagenci_koszt_proc": procent(koszt_pod, koszt),
            "podagenci_opus_koszt_proc": procent(koszt_pod_opus, koszt_pod),
            "wybudzenia": len(wybudzenia),
            "wybudzenia_koszt_usd": round(sum(w["koszt"] for w in wybudzenia), 2),
            "kontekst_startowy_mediana": round(m_start) if m_start is not None else None,
        },
        "koszt": koszt,
        "cache_trafienia_proc": procent(sum(w["odczyt"] for w in w_oknie), wejscie),
        "wyjscie_tokeny": sum(w["wyjscie"] for w in w_oknie),
        "modele": collections.Counter({m: round(sum(w["koszt"] or 0 for w in w_oknie if w["model"] == m), 2)
                                       for m in {w["model"] for w in w_oknie}}),
        "wybudzenia": sorted(wybudzenia, key=lambda w: w["czas"]),
        "nieznane_modele": {m: n for m, n in nieznane.items() if n},
        "sesje_startowe": len(startowe),
        "cennik_stan_na": cennik.get("stan_na", "?"),
    }


# ---------------------------------------------------------------- git i GitHub

def uruchom(polecenie, cwd):
    try:
        r = subprocess.run(polecenie, cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
        return r.returncode, r.stdout, r.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, "", str(e)


def bez_sesji(czas, aktywnosc: list) -> bool:
    """Czy w odstępie MARGINES_SESJI_MIN od `czas` nie ma żadnego zapisu lokalnej transkrypcji (lista posortowana)."""
    margines = dt.timedelta(minutes=MARGINES_SESJI_MIN)
    i = bisect.bisect_left(aktywnosc, czas - margines)
    return not (i < len(aktywnosc) and aktywnosc[i] <= czas + margines)


def git_i_gh(repozytoria: dict, od, do, gh, aktywnosc: dict = None):
    """Git i GitHub w oknie [od, do) (czas lokalny, z godziną). `aktywnosc`: nazwa repo -> posortowane czasy
    zapisów lokalnych transkrypcji jego sesji (do commitów i PR-ów bez lokalnej sesji)."""
    aktywnosc = aktywnosc or {}
    od_data, do_data = od.date(), (do - dt.timedelta(seconds=1)).date()
    wynik = {}
    for nazwa, sciezka in repozytoria.items():
        if not pathlib.Path(sciezka, ".git").exists():
            continue
        r = {"commity": 0, "commity_fix": 0, "reverty": 0, "zmiany_regul": 0, "za_zdalna": None,
             "commity_bez_sesji": 0, "pr_bez_sesji": 0,
             "pr_otwarte": 0, "pr_scalone": 0, "pr_h_do_scalenia": [], "pr_commity": [],
             "ci_wszystkie": 0, "ci_porazki": 0, "gh": "ok" if gh else "pominięty (brak gh albo --bez-gh)"}
        czasy = aktywnosc.get(nazwa, [])
        # Checkout w tyle za zdalną gałęzią (wg ostatniego fetch; skrypt sam nie łączy się z siecią):
        # pliki reguł czytane z dysku mogą być wtedy nieaktualne.
        kod, out, _ = uruchom(["git", "rev-list", "--count", "HEAD..@{u}"], sciezka)
        if kod == 0 and out.strip().isdigit():
            r["za_zdalna"] = int(out.strip())
        zakres = [f"--since={od.isoformat()}", f"--until={(do - dt.timedelta(seconds=1)).isoformat()}"]
        kod, out, _ = uruchom(["git", "log", "--all", "--no-merges", "--format=%H%x09%cI%x09%s", *zakres], sciezka)
        if kod == 0:
            linie = {}
            for l in out.splitlines():
                czesci = l.split("\t", 2)
                if len(czesci) == 3:
                    linie[czesci[0]] = (czas_lokalny(czesci[1]), czesci[2])
            r["commity"] = len(linie)
            r["commity_fix"] = sum(1 for _, t in linie.values() if re.match(r"fix", t, re.I))
            r["reverty"] = sum(1 for _, t in linie.values() if t.lower().startswith("revert"))
            r["commity_bez_sesji"] = sum(1 for c, _ in linie.values() if c and bez_sesji(c, czasy))
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
                    if utw and od <= utw < do:
                        r["pr_otwarte"] += 1
                        r["pr_bez_sesji"] += bez_sesji(utw, czasy)
                    if scal and od <= scal < do:
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
                    if c and od <= c < do and run.get("conclusion"):
                        r["ci_wszystkie"] += 1
                        r["ci_porazki"] += run["conclusion"] in ("failure", "timed_out", "startup_failure")
        wynik[nazwa] = r
    return wynik


def osobny_katalog(sciezka, korzen, konf: dict):
    """Katalog z `katalogi_regul_osobno` (np. `repo-roots/` z kopiami CLAUDE.md dla przyszłych repozytoriów),
    w którym leży plik reguł, albo None. Wpisy są względne wobec korzenia repo, z ukośnikiem albo bez."""
    try:
        wzgledna = pathlib.Path(sciezka).relative_to(korzen).as_posix()
    except ValueError:
        return None
    for w in konf.get("katalogi_regul_osobno") or []:
        w = w.replace("\\", "/").strip("/")
        if w and wzgledna.startswith(w + "/"):
            return w + "/"
    return None


def podejrzane_kopie_regul(regul: list, korzenie: dict, prog: int = 3) -> list:
    """Katalogi pierwszego poziomu repo z co najmniej `prog` zagnieżdżonymi CLAUDE.md, liczone w liniach reguł:
    kandydaci do `katalogi_regul_osobno`. Zwraca [(repo, katalog, pliki, linie)]."""
    grupy = collections.defaultdict(lambda: [0, 0])
    for nazwa, sciezka, linie, osobno in regul:
        if osobno or nazwa not in korzenie:
            continue
        try:
            czesci = pathlib.Path(sciezka).relative_to(korzenie[nazwa]).parts
        except ValueError:
            continue
        if len(czesci) >= 3:
            grupy[(nazwa, czesci[0])][0] += 1
            grupy[(nazwa, czesci[0])][1] += linie
    return [(n, k + "/", p, l) for (n, k), (p, l) in sorted(grupy.items()) if p >= prog]


def pliki_regul(repozytoria: dict, konf: dict) -> list:
    """Lista (repo, ścieżka, linie, osobny katalog albo None)."""
    pliki = [("globalne", wspolne.katalog_claude() / "CLAUDE.md")]
    for nazwa, sciezka in repozytoria.items():
        baza = pathlib.Path(sciezka)
        for wzor in ("CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md", "*/CLAUDE.md"):
            pliki += [(nazwa, p) for p in sorted(baza.glob(wzor))]
        # Śledzone CLAUDE.md na dowolnej głębokości (np. mitm/db/CLAUDE.md); bez przeszukiwania vendor/ i node_modules/.
        kod, out, _ = uruchom(["git", "-c", "core.quotepath=off", "ls-files", "--", "CLAUDE.md", "*/CLAUDE.md"], sciezka)
        if kod == 0:
            pliki += [(nazwa, baza / wzgledna) for wzgledna in sorted(out.splitlines()) if wzgledna]
    pliki += [("dodatkowe", pathlib.Path(p).expanduser()) for p in konf.get("pliki_regul_dodatkowe") or []]
    wynik, widziane = [], set()
    for nazwa, p in pliki:
        try:
            klucz = str(p.resolve()).lower()
            if klucz in widziane or not p.is_file():
                continue
            widziane.add(klucz)
            osobno = osobny_katalog(p, repozytoria[nazwa], konf) if nazwa in repozytoria else None
            wynik.append((nazwa, str(p), len(p.read_text(encoding="utf-8", errors="replace").splitlines()), osobno))
        except OSError:
            pass
    return wynik


def pamiec(foldery, od, projekty_folderow: dict):
    """Pliki pamięci w folderach transkrypcji: liczba, zmienione w oknie, foldery z pamięcią bez sesji w oknie."""
    liczba, zmiany, bez_sesji = 0, [], []
    for folder in foldery:
        w_folderze = 0
        for p in (folder / "memory").glob("*.md"):
            if p.name == "MEMORY.md":
                continue
            w_folderze += 1
            zm = dt.datetime.fromtimestamp(p.stat().st_mtime).astimezone()
            if zm >= od:
                zmiany.append((projekty_folderow.get(folder, folder.name[-40:]), p.name, zm))
        liczba += w_folderze
        if w_folderze and folder not in projekty_folderow:
            bez_sesji.append((folder.name[-40:], w_folderze))
    return liczba, sorted(zmiany, key=lambda x: x[2]), bez_sesji


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
          "| sesja | tytuł | aktywna | wiad. wł. | pytania (rek/inna/własna/odł.) | przerw. | blokady | błędy | kompakty | podagenci | koszt API |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in sesje:
        c = s.licz
        koszt = "—" if s.koszt is None else f"${s.koszt:.2f}"
        l.append(f"| `{s.sid[:8]}` | {s.tytul or '—'} | {s.pierwszy:%m-%d %H:%M} – {s.ostatni:%m-%d %H:%M} | "
                 f"{c['wiad_wlasciciela']} | {c['pytania']} ({c['pyt_rekomendowana']}/{c['pyt_inna']}/{c['pyt_wlasna']}/{c['pyt_odlozone']}) | "
                 f"{c['przerwania']} | {c['blokady_klasyfikatora']} | {c['bledy_narzedzi']} | {c['kompakty']} | {c['podagenci']} | {koszt} |")
    l += ["", "## Oś czasu", "",
          "Legenda: **[K?]** = heurystycznie możliwa korekta; klasy odpowiedzi: rekomendowana / inna / własna "
          "(tekst spoza opcji) / odłożone / bez wyboru / fakt (pytanie z „[fakt]”).", ""]
    zdarzenia = sorted(((czas, s, r, d) for s in sesje for czas, r, d in s.zdarzenia), key=lambda x: x[0])
    for czas, s, rodzaj, d in zdarzenia:
        znak = f"`{czas:%m-%d %H:%M}` `{s.sid[:8]}`"
        if rodzaj == "wlasciciel":
            w_trakcie = " (w trakcie pracy Claude'a)" if d.get("w_trakcie") else ""
            l.append(f"- {znak} **Właściciel{w_trakcie}{' [K?]' if d['korekta'] else ''}:** {d['tekst']}")
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


def tys(n) -> str:
    return "—" if n is None else f"{n / 1000:.0f}k"


def raport_tokenow(tok: dict, sesje: list) -> list:
    m = tok["metryki"]
    proc = lambda v: "—" if v is None else f"{v}%"  # noqa: E731
    l = ["", "## Tokeny i koszt (ceny API, miara względna)", "",
         f"Ceny z `references/cennik.json` (stan na {tok['cennik_stan_na']}; nadpisuje je pole `cennik` w konfiguracji). "
         "To miara względna, nie rachunek: konto na subskrypcji płaci limitem. Dolne oszacowanie, bo wywołania spoza "
         "transkrypcji (klasyfikator trybu auto, tytuły sesji) nie są liczone. Wywołanie = unikalny `message.id`, "
         "razem z transkrypcjami podagentów. Szczegóły i ograniczenia: `references/sygnaly.md`.", "",
         "| | wartość |", "|---|---|",
         f"| wywołania API | {m['wywolania_api']} |",
         f"| koszt | ${m['koszt_api_usd']:.2f} |",
         f"| trafienia cache (odczyt / cały kontekst) | {proc(tok['cache_trafienia_proc'])} |",
         f"| tokeny wyjścia | {tok['wyjscie_tokeny']} |",
         f"| mediana kontekstu sesji głównej | {tys(m['kontekst_mediana'])} |",
         f"| wywołania sesji głównej > {PROG_DUZEGO_KONTEKSTU // 1000}k | {proc(m['kontekst_ponad_200k_proc'])} |",
         f"| kontekst startowy, mediana ({tok['sesje_startowe']} sesji zaczętych w oknie) | {tys(m['kontekst_startowy_mediana'])} |",
         f"| udział podagentów w koszcie | {proc(m['podagenci_koszt_proc'])} |",
         f"| udział Opusa w koszcie podagentów | {proc(m['podagenci_opus_koszt_proc'])} |",
         f"| wybudzenia (zapis cache > {PROG_WYBUDZENIA_TOKENY // 1000}k po przerwie > {PROG_WYBUDZENIA_H} h) | "
         f"{m['wybudzenia']} (${m['wybudzenia_koszt_usd']:.2f}) |"]
    if tok["modele"]:
        l += ["", "Koszt wg modelu: " + ", ".join(f"{k} ${v:.2f}" for k, v in tok["modele"].most_common()) + "."]
    drogie = sorted((s for s in sesje if s.koszt), key=lambda s: -s.koszt)[:5]
    if drogie:
        l += ["", "Najdroższe sesje:", ""]
        l += [f"- `{s.sid[:8]}` {s.projekt[0]}, {s.tytul or '—'}: ${s.koszt:.2f}" for s in drogie]
    if tok["wybudzenia"]:
        l += ["", "Wybudzenia (koszt samego zapisu cache):", ""]
        l += [f"- `{w['czas']:%m-%d %H:%M}` `{w['sesja'].sid[:8]}` po {w['przerwa_h']:.1f} h: zapis {tys(w['zapis'])}, ${w['koszt']:.2f}"
              for w in tok["wybudzenia"]]
    if tok["nieznane_modele"]:
        l += ["", "**Uwaga:** modeli bez ceny w cenniku nie wliczono do kosztu: " + ", ".join(
            f"`{k}` ({n} wywołań)" for k, n in sorted(tok["nieznane_modele"].items())) + ". Dopisz je do pola `cennik` "
            "w konfiguracji albo do `references/cennik.json` w repo pluginu."]
    return l


def retencja_dni() -> int:
    """Po ilu dniach Claude Code usuwa transkrypcje (`cleanupPeriodDays` w ustawieniach użytkownika, domyślnie 30)."""
    try:
        ustawienia = json.loads((wspolne.katalog_claude() / "settings.json").read_text(encoding="utf-8"))
        return int(ustawienia.get("cleanupPeriodDays", 30))
    except (OSError, ValueError, TypeError, AttributeError):
        return 30


def zakonczenie_retro(katalog, od_data):
    """Czas commita, którym retro zakończone w dniu `od_data` dostało „**Status:** zakończone”:
    (czas lokalny, opis) albo None. Gdy tego dnia zakończono kilka retro, bierze najpóźniejsze."""
    if katalog is None:
        return None
    najpozniej = None
    for numer, _, plik in wspolne.retro_zakonczone(pathlib.Path(katalog) / "retro"):
        # pierwszy commit, który dodał linię statusu „zakończone” (-G: zmiana linii pasującej do wzoru)
        kod, out, _ = uruchom(["git", "log", "--reverse", "--format=%cI%x09%h",
                               r"-G\*\*Status:\*\*[[:space:]]*zako", "--", plik.name], str(plik.parent))
        if kod != 0 or not out.strip():
            continue
        czas_s, hash_ = out.splitlines()[0].split("\t", 1)
        czas = czas_lokalny(czas_s)
        if czas and czas.date() == od_data and (najpozniej is None or czas > najpozniej[0]):
            najpozniej = (czas.replace(microsecond=0), f"R{numer:02d} (commit `{hash_}`)")
    return najpozniej


def nazwa_pliku(nazwa: str) -> str:
    return re.sub(r"[^\w.-]+", "-", nazwa).strip("-") or "projekt"


def main(argv=None):
    for strumien in (sys.stdout, sys.stderr):
        try:
            strumien.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--od", required=True,
                    help="początek okna: RRRR-MM-DD (lokalnie, włącznie) albo RRRR-MM-DDTGG:MM")
    ap.add_argument("--do", help="ostatni dzień okna (włącznie); domyślnie dziś")
    ap.add_argument("--od-poczatku-dnia", action="store_true",
                    help="okno od północy dnia --od, także gdy tego dnia zakończono retro")
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
        sys.exit("Nie znaleziono katalogu roboczego retro. Załóż go skryptem zaloz.py --tryb konto|projekt (patrz SKILL.md).")
    konf = wspolne.wczytaj_konfiguracje(katalog)

    try:
        if len(a.od) > 10:
            od = dt.datetime.fromisoformat(a.od.replace(" ", "T")).replace(second=0, microsecond=0).astimezone()
            od_data, poczatek = od.date(), "podany w `--od`"
        else:
            od_data = dt.date.fromisoformat(a.od)
            od, poczatek = dt.datetime.combine(od_data, dt.time()).astimezone(), "od północy"
            retro = None if a.od_poczatku_dnia else zakonczenie_retro(katalog, od_data)
            if retro:
                od, poczatek = retro[0], f"od commita, który zakończył {retro[1]}"
        do_data = dt.date.fromisoformat(a.do) if a.do else dt.date.today()
    except ValueError as e:
        sys.exit(f"Zła data w --od/--do: {e}")
    do = dt.datetime.combine(do_data + dt.timedelta(days=1), dt.time()).astimezone()
    wyjscie = pathlib.Path(a.wyjscie) if a.wyjscie else katalog / "dane" / f"sygnaly-{od_data}_{do_data}"
    wyjscie.mkdir(parents=True, exist_ok=True)

    projekty = Projekty(konf)
    sesje, w_scratchpadzie = wszystkie_sesje(od, do, projekty, konf)

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
    tok = metryki_tokenow(sesje, od, do, wczytaj_cennik(konf))
    per_projekt = collections.defaultdict(list)
    for s in sesje:
        per_projekt[s.projekt[0]].append(s)
    zamazane = 0
    for nazwa, lista in per_projekt.items():
        lista.sort(key=lambda s: s.pierwszy)
        tresc, n = zamaz(raport_projektu(nazwa, lista, od_data, do_data))
        zamazane += n
        (wyjscie / f"{nazwa_pliku(nazwa)}.md").write_text(tresc, encoding="utf-8")

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
    aktywnosc = {nazwa: sorted(c for s in lista for c in s.czasy) for nazwa, lista in per_projekt.items()}
    repo = git_i_gh(repozytoria, od, do, gh, aktywnosc)
    regul = pliki_regul(repozytoria, konf)
    kopie_regul = podejrzane_kopie_regul(regul, repozytoria)
    projekty_folderow = {}
    for s in sesje:
        projekty_folderow.setdefault(s.folder, s.projekt[0])
    if repo_projektu or wybrane:
        foldery = sorted(projekty_folderow)
    else:
        foldery = sorted(p for p in (wspolne.katalog_claude() / "projects").glob("*") if p.is_dir())
    pamiec_liczba, pamiec_zmiany, pamiec_bez_sesji = pamiec(foldery, od, projekty_folderow)

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
        "claude_md_linie": sum(n for _, _, n, osobno in regul if not osobno), "pamiec_pliki": pamiec_liczba,
        # od 0.1.3; w metryki.csv dopisane na końcu, za zobowiazania_aktywne
        "okno_od_godzina": f"{od:%H:%M}", "pyt_fakt": suma["pyt_fakt"],
        **tok["metryki"],
        "koszt_na_wiadomosc_usd": round(tok["koszt"] / suma["wiad_wlasciciela"], 2) if suma["wiad_wlasciciela"] else None,
        "commity_bez_sesji": sum(r["commity_bez_sesji"] for r in repo.values()),
        "pr_bez_sesji": sum(r["pr_bez_sesji"] for r in repo.values()),
        "claude_md_linie_osobno": sum(n for _, _, n, osobno in regul if osobno),
    }
    (wyjscie / "metryki.json").write_text(json.dumps(metryki, ensure_ascii=False, indent=2), encoding="utf-8")

    zakres = f"projekt `{repo_projektu}`" if repo_projektu else "całe konto (wszystkie projekty z transkrypcji)"
    if wybrane:
        zakres += f", zawężone do: {', '.join(sorted(wybrane))}"
    l = [f"# Sygnały do retro: {od_data} … {do_data}", "",
         f"Wygenerowano {dt.datetime.now():%Y-%m-%d %H:%M} skryptem `scripts/sygnaly.py` skillu retro. Zakres: {zakres}. "
         "Liczby z heurystyk (np. „możliwa korekta”) są wskazówką, nie dowodem: dowodem jest wpis w osi czasu projektu.", "",
         f"Okno: {od:%Y-%m-%d %H:%M} … {do_data} 23:59 ({poczatek}).", "",
         f"Wiadomości właściciela wysłane w trakcie pracy Claude'a: {suma['wiad_w_trakcie']} (wliczone w `wiad_wlasciciela`). "
         f"Pominięte sesje uruchomione w scratchpadzie (np. testy `claude -p`): {w_scratchpadzie}. "
         f"Ciągi wyglądające na sekrety zamazane w osiach czasu: {zamazane} (heurystyka; patrz `references/sygnaly.md`).", "",
         ]
    retencja = retencja_dni()
    if retencja > 0 and (dt.date.today() - od_data).days > retencja:
        l += [f"**Uwaga:** okno zaczyna się {(dt.date.today() - od_data).days} dni temu, a Claude Code usuwa transkrypcje "
              f"starsze niż {retencja} dni (`cleanupPeriodDays`). Sesje sprzed {dt.date.today() - dt.timedelta(days=retencja)} "
              "mogły już zniknąć z dysku, więc liczby dla początku okna są zaniżone.", ""]
    l += ["## Metryki", "", "| metryka | wartość |", "|---|---|"]
    l += [f"| {k} | {v} |" for k, v in metryki.items()]
    l += ["", "## Projekty", "", "| projekt | sesje | wiad. wł. | [K?] | pytania | rek. | inna | własna | odłożone | fakt | przerw. | blokady | błędy | kompakty | podagenci | koszt API |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for nazwa, lista in sorted(per_projekt.items()):
        c = collections.Counter()
        for s in lista:
            c.update(s.licz)
        koszt = sum(s.koszt or 0 for s in lista)
        l.append(f"| [{nazwa}]({nazwa_pliku(nazwa)}.md) | {len(lista)} | {c['wiad_wlasciciela']} | {c['wiad_mozliwa_korekta']} | {c['pytania']} | "
                 f"{c['pyt_rekomendowana']} | {c['pyt_inna']} | {c['pyt_wlasna']} | {c['pyt_odlozone']} | {c['pyt_fakt']} | {c['przerwania']} | "
                 f"{c['blokady_klasyfikatora'] + c['blokady_u_podagentow']} | {c['bledy_narzedzi']} | {c['kompakty']} | {c['podagenci']} | ${koszt:.2f} |")
    l += ["", "## Pora wiadomości właściciela", ""] + [f"- {k}: {v}" for k, v in sorted(pory.items())]
    l += raport_tokenow(tok, sesje)
    l += ["", "## Repozytoria", "", "| repo | ścieżka | commity | bez lok. sesji | fix | revert | zmiany reguł | PR otw. | bez lok. sesji | PR scal. | mediana h do scalenia | mediana commitów/PR | CI porażki/wszystkie | za zdalną | gh |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for nazwa, r in repo.items():
        med_h = statistics.median(r["pr_h_do_scalenia"]) if r["pr_h_do_scalenia"] else "—"
        med_c = statistics.median(r["pr_commity"]) if r["pr_commity"] else "—"
        za = "—" if r["za_zdalna"] is None else r["za_zdalna"]
        l.append(f"| {nazwa} | `{repozytoria[nazwa]}` | {r['commity']} | {r['commity_bez_sesji']} | {r['commity_fix']} | {r['reverty']} | "
                 f"{r['zmiany_regul']} | {r['pr_otwarte']} | {r['pr_bez_sesji']} | "
                 f"{r['pr_scalone']} | {med_h} | {med_c} | {r['ci_porazki']}/{r['ci_wszystkie']} | {za} | {r['gh']} |")
    poza = [(nazwa, r) for nazwa, r in repo.items()
            if (r["commity_bez_sesji"] >= 3 and r["commity_bez_sesji"] >= 0.2 * r["commity"])
            or (r["pr_bez_sesji"] >= 2 and r["pr_bez_sesji"] >= 0.2 * r["pr_otwarte"])]
    if poza:
        l += ["", "**Uwaga:** część pracy w repozytoriach nie ma lokalnych transkrypcji (brak zapisu sesji tego repo w odstępie "
              f"±{MARGINES_SESJI_MIN} min): " + "; ".join(
                  f"{n}: {r['commity_bez_sesji']} z {r['commity']} commitów"
                  + (f", {r['pr_bez_sesji']} z {r['pr_otwarte']} otwartych PR" if r["pr_otwarte"] else "")
                  for n, r in poza) + ". "
              "To zwykle sandbox, sesje w chmurze, inna maszyna albo scalenia na GitHubie. Osie czasu, pytania i koszt tej "
              "pracy nie widzą, więc nie zestawiaj ich z commitami tych repo (np. koszt na PR). Transkrypcje skopiowane "
              "z innej maszyny dołącza pole `transkrypcje_dodatkowe` w konfiguracji."]
    l += ["", "## Pliki reguł (linie)", ""] + [f"- {n} `{p}`: {k}" for n, p, k, osobno in regul if not osobno]
    osobne = [(n, p, k, osobno) for n, p, k, osobno in regul if osobno]
    if osobne:
        l += ["", f"Liczone osobno (`katalogi_regul_osobno`), poza `claude_md_linie`: "
              f"{sum(k for _, _, k, _ in osobne)} linii w {len(osobne)} plikach.", ""]
        l += [f"- {n} `{p}`: {k}" for n, p, k, _ in osobne]
    if kopie_regul:
        l += ["", "**Uwaga:** katalogi z wieloma zagnieżdżonymi `CLAUDE.md`, liczone w `claude_md_linie`: " + "; ".join(
            f"{n} `{k}`: {p} plików, {li} linii" for n, k, p, li in kopie_regul) + ". Jeśli to kopie dla przyszłych "
            "repozytoriów (a nie reguły, które ładują sesje w tym repo), dopisz katalog do `katalogi_regul_osobno`."]
    w_tyle = [(nazwa, r["za_zdalna"]) for nazwa, r in repo.items() if r["za_zdalna"]]
    if w_tyle:
        l += ["", "**Uwaga:** checkout jest za zdalną gałęzią (wg ostatniego `git fetch`), więc liczby linii reguł i ich treść "
              "na dysku mogą być nieaktualne: " + ", ".join(f"{n} o {k} commitów" for n, k in w_tyle) + ". "
              "Czytaj reguły z `git show @{u}:CLAUDE.md`."]
    l += ["", "Liczone są pliki `CLAUDE.md` (śledzone na dowolnej głębokości), `CLAUDE.local.md` i `pliki_regul_dodatkowe` "
          "z konfiguracji. Inne pliki, do których reguły odsyłają jako wiążących, dopisz do `pliki_regul_dodatkowe`; "
          "katalogi z kopiami reguł dla innych repozytoriów do `katalogi_regul_osobno`."]
    l += ["", f"## Pamięć: {pamiec_liczba} plików, zmienione w oknie: {len(pamiec_zmiany)}", ""]
    l += [f"- `{zm:%m-%d %H:%M}` {proj} / {nazwa}" for proj, nazwa, zm in pamiec_zmiany]
    if pamiec_bez_sesji:
        l += ["", "Projekty z pamięcią, ale bez lokalnej sesji w oknie (praca gdzie indziej albo projekt uśpiony; "
              "ich repo i pliki reguł nie są tu liczone, dodaj je w `repozytoria_dodatkowe`):", ""]
        l += [f"- …{folder}: {n} plików pamięci" for folder, n in pamiec_bez_sesji]
    tresc, n = zamaz("\n".join(l) + "\n")
    (wyjscie / "podsumowanie.md").write_text(tresc, encoding="utf-8")
    print(f"OK: {len(sesje)} sesji, {len(per_projekt)} projektów, {len(repo)} repo, zamazane sekrety: {zamazane + n} -> {wyjscie}")
    return metryki


if __name__ == "__main__":
    main()
