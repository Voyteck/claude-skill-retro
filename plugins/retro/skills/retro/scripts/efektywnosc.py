"""Tokeny i efektywność pisania: koszt wg roli agenta i modelu, rundy poprawek w scalonych PR, powroty od przeglądu
i CI, porównanie z poprzednimi retro. Używa go `sygnaly.py` (sekcja „Tokeny i efektywność” podsumowania).

Role agentów rozpoznaje po typie podagenta (`subagent_type`) wzorcami z pola `role_agentow` konfiguracji
(domyślnie ROLE_DOMYSLNE); sesja główna ma rolę `sesja`, nierozpoznany podagent `inne`. Ograniczenia pomiaru:
`references/sygnaly.md`, sekcja „Tokens and writing efficiency”.
"""
import collections
import csv
import datetime as dt
import json
import pathlib
import re
import statistics
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import tokeny  # noqa: E402
import teksty  # noqa: E402
from teksty import t  # noqa: E402

# Kolejność ma znaczenie: pierwsza pasująca rola wygrywa (np. „architekt-przeglad” to przegląd).
ROLE_DOMYSLNE = {
    "implementacja": ["programista", "implement", "developer", "coder", "engineer"],
    "przeglad": ["przeglad", "przegląd", "review", "tester", "qa", "audit"],
    "ci": ["obserwator", r"\bci\b", "watch"],
    "architekt": ["architekt", "architect"],
}
RODZINY = ("fable", "mythos", "opus", "sonnet", "haiku")
# Rundy poprawek: przerwa między paczkami commitów, pomijane gałęzie (partie integracyjne), za duże PR.
PRZERWA_RUNDY_MIN, MAX_COMMITOW, POMIN_GALEZIE, TYGODNIE = 20, 40, ["integration/", "batch/"], 6
MAX_STRON_GH = 10
# Porównanie z poprzednimi retro (kolumny `metryki.csv`); dla każdego wskaźnika więcej = gorzej.
POROWNANIE = ["koszt_na_wiadomosc_usd", "tokeny_wyjscia_na_wiadomosc", "znaki_do_wlasciciela_na_wiadomosc",
              "znaki_promptu_agenta", "kontekst_mediana", "kontekst_ponad_200k_proc", "kontekst_startowy_mediana",
              "podagenci_opus_koszt_proc", "wybudzenia_koszt_usd", "pr_z_poprawka_proc", "rundy_na_pr",
              "powroty_przeglad", "powroty_ci", "koszt_na_pr_usd", "pliki_kontekstu_tokeny"]
POPRZEDNIE_RETRO = 3
# Rozmiar PR (dodane + usunięte linie): S do pierwszego progu, M do drugiego, L powyżej.
PROGI_ROZMIARU = [50, 300]
# Konfiguracja implementatora ma wynik, a nie tylko wskazówkę, od tylu PR w komórce tabeli.
MIN_PR = 5
# Ostrzeżenie o możliwej zmianie repo pracy: koszt tygodnia od tej kwoty (USD; pole `ostrzezenie_koszt_tygodnia_usd`),
# a PR brak albo koszt na PR tyle razy powyżej mediany innych tygodni.
PROG_KOSZTU_TYGODNIA, KROTNOSC_KOSZTU_NA_PR = 100, 3
ZAPYTANIE_PR = """
query($q: String!, $po: String) {
  search(query: $q, type: ISSUE, first: 40, after: $po) {
    pageInfo { hasNextPage endCursor }
    nodes { ... on PullRequest {
      number createdAt mergedAt headRefName additions deletions changedFiles
      commits(first: 100) { totalCount nodes { commit { oid authoredDate messageHeadline messageBody
        parents { totalCount } } } }
    } }
  }
}"""
WZOR_MODELU = re.compile(r"Co-Authored-By:\s*Claude\s+([A-Za-z]+)", re.I)
# Stopka `Agent: <nazwa>` (od 0.7.2, konwencja opcjonalna): model brany z definicji agenta, mocniejszy od `Co-Authored-By`,
# bo agent dziedziczący stopkę z szablonu podpisuje się modelem sesji, nie swoim.
WZOR_AGENTA = re.compile(r"^Agent:\s*([\w.-]+)", re.I | re.M)


# ---------------------------------------------------------------- role i modele

def wzorce_rol(konf: dict) -> list:
    role = konf.get("role_agentow") or ROLE_DOMYSLNE
    return [(r, re.compile("|".join(w), re.IGNORECASE)) for r, w in role.items() if w]


def rola(podagent: bool, agent, wzorce: list) -> str:
    if not podagent:
        return "sesja"
    for nazwa, wzor in wzorce:
        if wzor.search(agent or ""):
            return nazwa
    return "inne"


def etykieta_roli(r: str) -> str:
    return t("rola_" + r) if "rola_" + r in teksty.TEKSTY else r


def rodzina(model) -> str:
    m = (model or "").lower()
    for r in RODZINY:
        if r in m:
            return r.capitalize()
    return model or "?"


def udzialy(licznik) -> str:
    """„Opus:90;Sonnet:10” (procent sumy, malejąco) albo None."""
    suma = sum(licznik.values())
    if not suma:
        return None
    return ";".join(f"{k}:{round(100 * v / suma)}" for k, v in licznik.most_common() if round(100 * v / suma))


# ---------------------------------------------------------------- koszt wg roli i modelu

def koszt_wg_roli(calls: dict, cennik: dict, wzorce: list, od_tygodnia: dt.date):
    """Z archiwum wywołań (`tokeny-archiwum*.json`): {(tydzień, rola, rodzina, poziom rozumowania): USD}
    i {tydzień: USD}. Ceny bieżących modeli rodziny (jak `koszt_api_usd_ceny_55`), żeby zmiana cennika nie udawała
    zmiany pracy. Poziom None = wywołanie bez zapisanego poziomu (starsze transkrypcje)."""
    tab, sumy = collections.defaultdict(float), collections.defaultdict(float)
    for x in rekordy_kosztu(calls, cennik, wzorce):
        tydz = tokeny.poniedzialek(x["czas"])
        if tydz < od_tygodnia:
            continue
        tab[(tydz, *x["klucz"])] += x["koszt"]
        sumy[tydz] += x["koszt"]
    return tab, sumy


def rekordy_kosztu(calls: dict, cennik: dict, wzorce: list) -> list:
    """Wywołania archiwum z kosztem w cenach bieżących modeli rodziny: wspólna definicja tygodni i okien."""
    wynik = []
    for r in calls.values():
        w = tokeny.z_rekordu(r)
        if not w["czas"]:
            continue
        c = tokeny.czesci_kosztu(w, cennik, tokeny.model_biezacy(w["model"], cennik))
        if not c:
            continue
        bez_odczytu = w["wejscie"] + w["wyjscie"] + w["zapis_5m"] + w["zapis_1h"]
        wynik.append({"czas": w["czas"], "koszt": sum(c.values()), "tokeny": bez_odczytu + w["odczyt"],
                      "bez_odczytu": bez_odczytu, "poziom": w.get("effort"),
                      "klucz": (rola(r.get("sub"), r.get("agent"), wzorce), rodzina(w["model"]), w.get("effort"))})
    return wynik


def koszt_okna(rekordy: list, od, do) -> collections.Counter:
    """{(rola, rodzina, poziom): USD} dla rekordów okna [od, do), liczone jak kolumny tygodni."""
    wynik = collections.Counter()
    for x in rekordy:
        if od <= x["czas"] < do:
            wynik[x["klucz"]] += x["koszt"]
    return wynik


def koszt_implementacji_wg_modelu(wywolania: list, wzorce: list):
    """Udział rodzin modeli w koszcie implementacji (wywołania okna z `metryki_tokenow`)."""
    licznik = collections.Counter()
    for w in wywolania:
        if rola(w["podagent"], w.get("agent"), wzorce) == "implementacja":
            licznik[rodzina(w["model"])] += w.get("koszt") or 0
    return udzialy(licznik)


def koszt_wg_poziomu(wywolania: list):
    """Udział poziomów rozumowania w koszcie okna, „high:80;xhigh:18;?:2” („?” = bez zapisanego poziomu)."""
    licznik = collections.Counter()
    for w in wywolania:
        licznik[w.get("effort") or "?"] += w.get("koszt") or 0
    return udzialy(licznik)


# ---------------------------------------------------------------- koszt i jakość na PR wg konfiguracji

def konfiguracja(model, poziom) -> str:
    return f"{rodzina(model)} · {poziom}" if poziom else rodzina(model)


def rozmiar(linie, progi=None) -> str:
    progi = progi or PROGI_ROZMIARU
    if linie is None:
        return "?"
    return "S" if linie <= progi[0] else "M" if linie <= progi[1] else "L"


def koszt_agenta(a: dict, cennik: dict) -> float:
    """Koszt podagenta z sum tokenów jego transkrypcji (`zdarzenia_agentow.py`), w cenach bieżącego modelu rodziny,
    bez dopłaty za długi kontekst (sumy nie mają kontekstu pojedynczych wywołań)."""
    tok = a.get("tokeny") or {}
    cw5 = tok["cw5"] if "cw5" in tok else tok.get("cw", 0)      # wynik sprzed 0.4.0: cały zapis po stawce 5 min
    w = {"model": a.get("model") or "?", "wejscie": tok.get("inp", 0), "wyjscie": tok.get("out", 0),
         "zapis_5m": cw5, "zapis_1h": tok.get("cw1h", 0), "odczyt": tok.get("cr", 0), "kontekst": 0,
         "fast": False, "web_search": 0}
    c = tokeny.czesci_kosztu(w, cennik, tokeny.model_biezacy(w["model"], cennik))
    return sum(c.values()) if c else 0.0


def koszty_pr(zrodla: list, wzorce: list, cennik: dict) -> dict:
    """{(repo albo None, nr PR): {"koszt": Counter(rola → USD), "impl": (typ, model, poziom, czas) pierwszego
    implementatora albo None, "typy": {typ agenta: [USD, czas pierwszej pracy]}}} ze zdarzeń agentów.
    `zrodla`: [(dane `zdarzenia_agentow`, {sesja: repo})]. Koszt agenta, który pracował nad kilkoma PR, dzieli się
    po równo."""
    wynik = collections.defaultdict(lambda: {"koszt": collections.Counter(), "impl": None, "typy": {}})
    for dane, repo_sesji in zrodla:
        agenci = dane.get("agenci") or {}
        prs = collections.defaultdict(set)
        for aid, a in agenci.items():
            prs[aid].update(a.get("pr") or [])
        for e in dane.get("zdarzenia") or []:
            if e.get("rodzaj") == "kontynuacja" and e.get("agent") in agenci:
                prs[e["agent"]].update(e.get("pr") or [])
        for aid, a in agenci.items():
            if not prs[aid]:
                continue
            r = rola(True, a.get("typ"), wzorce)
            k = koszt_agenta(a, cennik) / len(prs[aid])
            poziom = (a.get("tokeny") or {}).get("eff") or a.get("effort_zadany")
            for pr in prs[aid]:
                rek = wynik[(repo_sesji.get(a.get("s")), pr)]
                rek["koszt"][r] += k
                typ = rek["typy"].setdefault(a.get("typ") or "?", [0.0, a.get("ts") or ""])
                typ[0] += k
                if a.get("ts") and (not typ[1] or a["ts"] < typ[1]):
                    typ[1] = a["ts"]
                if r == "implementacja" and (rek["impl"] is None or (a.get("ts") or "") < rek["impl"][3]):
                    rek["impl"] = (a.get("typ"), a.get("model"), poziom, a.get("ts") or "")
    return dict(wynik)


def polacz_pr(rundy: list, koszty: dict) -> list:
    """Rekordy `rundy_pr` z kosztem agentów i konfiguracją implementatora (`pr_koszt`, `pr_impl`). Dopasowanie po
    (repo, nr); PR ze źródła bez repo (np. kontener) po samym numerze, gdy jest jednoznaczny wśród PR z GitHuba."""
    numery = collections.Counter(r["pr"] for r in rundy)
    bez_repo = collections.defaultdict(list)
    for (repo, pr), rek in koszty.items():
        if repo is None:
            bez_repo[pr].append(rek)
    wynik = []
    for r in rundy:
        reki = ([koszty[(r["repo"], r["pr"])]] if (r["repo"], r["pr"]) in koszty else []) \
            + (bez_repo.get(r["pr"], []) if numery[r["pr"]] == 1 else [])
        koszt, impl, typy = collections.Counter(), None, {}
        for rek in reki:
            koszt.update(rek["koszt"])
            for typ, (k, ts) in (rek.get("typy") or {}).items():
                stary = typy.setdefault(typ, [0.0, ""])
                stary[0] += k
                if ts and (not stary[1] or ts < stary[1]):
                    stary[1] = ts
            if rek["impl"] and (impl is None or rek["impl"][3] < impl[3]):
                impl = rek["impl"]
        wynik.append(dict(r, pr_koszt=koszt if reki else None, pr_impl=impl, pr_typy=typy if reki else None))
    return wynik


def opis_konfiguracji(lista: list) -> dict:
    """PR, odsetek z poprawką, rundy, koszt implementacji, przeglądu i CI oraz całkowity na PR (średnia = oczekiwany
    koszt zaakceptowanego PR, bo zawiera rundy poprawek z ich częstością), koszt na 100 linii."""
    o = opis_pr(lista)
    koszty = [sum(r["pr_koszt"].values()) for r in lista]
    linie = sum(r["linie"] or 0 for r in lista)
    o.update({"impl": statistics.mean(r["pr_koszt"]["implementacja"] for r in lista) if lista else None,
              "kontrola": statistics.mean(r["pr_koszt"]["przeglad"] + r["pr_koszt"]["ci"] for r in lista) if lista else None,
              "na_pr": statistics.mean(koszty) if koszty else None,
              "na_100_linii": 100 * sum(koszty) / linie if linie else None})
    return o


def tabela_konfiguracji(polaczone: list, progi=None) -> dict:
    """{(konfiguracja implementatora, rozmiar): [PR]} dla PR z kosztem agentów."""
    grupy = collections.defaultdict(list)
    for r in polaczone:
        if r["pr_koszt"] is None:
            continue
        impl = r["pr_impl"]
        etykieta = konfiguracja(impl[1], impl[2]) if impl else t("rola_sesja")
        grupy[(etykieta, rozmiar(r["linie"], progi))].append(r)
    return grupy


def konfiguracja_agentow(katalogi: list) -> list:
    """[(nazwa, model, poziom, źródło)] z nagłówków `.claude/agents/*.md` (szczegóły: `agenci.wczytaj_definicje`)."""
    import agenci
    return [(d["agent"], d["model"], d["effort"] or None, d["zrodlo"]) for d in agenci.wczytaj_definicje(katalogi)]


# ---------------------------------------------------------------- rundy poprawek w scalonych PR

def _uruchom(polecenie, cwd=None, env=None):
    try:
        r = subprocess.run(polecenie, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=180, env=env)
        return r.returncode, r.stdout, r.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, "", str(e)


def pr_commity(sciezka: str, od_data: dt.date, do_data: dt.date, gh: str, env: dict = None):
    """Scalone PR repo z commitami (data autorstwa, nagłówek, modele ze stopek `Co-Authored-By: Claude <Model>`):
    (lista, None) albo (None, błąd). `gh api graphql` z wyszukiwaniem po 40, bo `gh pr list --json commits`
    przekracza limit węzłów GraphQL."""
    kod, out, err = _uruchom([gh, "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"], sciezka, env)
    if kod != 0 or not out.strip():
        return None, (err or out).strip()[:160] or "gh repo view"
    repo, wynik, po = out.strip(), [], None
    for _ in range(MAX_STRON_GH):
        arg = [gh, "api", "graphql", "-f", "query=" + ZAPYTANIE_PR,
               "-f", f"q=repo:{repo} is:pr is:merged merged:{od_data.isoformat()}..{do_data.isoformat()}"]
        if po:
            arg += ["-f", "po=" + po]
        kod, out, err = _uruchom(arg, sciezka, env)
        if kod != 0:
            return None, err.strip()[:160]
        try:
            s = json.loads(out)["data"]["search"]
        except (ValueError, KeyError, TypeError):
            return None, out[:160]
        for n in s["nodes"]:
            if not n:
                continue
            commity = [{"ts": c["commit"]["authoredDate"], "naglowek": c["commit"]["messageHeadline"][:90],
                        "scalenie": c["commit"]["parents"]["totalCount"] > 1,
                        "modele": sorted({rodzina(m) for m in WZOR_MODELU.findall(c["commit"].get("messageBody") or "")}),
                        "agent": (WZOR_AGENTA.findall(c["commit"].get("messageBody") or "") or [None])[-1]}
                       for c in n["commits"]["nodes"]]
            wynik.append({"repo": repo, "pr": n["number"], "utworzony": n["createdAt"], "scalony": n["mergedAt"],
                          "galaz": n["headRefName"], "commitow": n["commits"]["totalCount"], "commity": commity,
                          "linie": (n.get("additions") or 0) + (n.get("deletions") or 0), "pliki": n.get("changedFiles")})
        if not s["pageInfo"]["hasNextPage"]:
            break
        po = s["pageInfo"]["endCursor"]
    return wynik, None


def modele_commita(c: dict, model_agenta=None) -> tuple:
    """(modele commita, rozbieżność). Ze stopką `Agent:` i znanym modelem agenta w dniu commita: model agenta;
    inaczej modele ze stopek `Co-Authored-By`. Rozbieżność: obie stopki są, a model agenta nie jest wśród nich."""
    czas = tokeny.czas_lokalny(c["ts"])
    model = model_agenta(c["agent"], czas.date()) if model_agenta and c.get("agent") and czas else None
    if not model:
        return c["modele"], False
    model = rodzina(model)
    return [model], bool(c["modele"]) and model not in c["modele"]


def rundy_pr(lista: list, konf: dict, model_agenta=None) -> list:
    """Rundy poprawek każdego PR: paczka commitów po przerwie > `pr_przerwa_rundy_min` to runda; pierwsza paczka to
    praca, kolejne to powroty. Model autora = najczęstszy model pierwszej paczki (None = bez stopki), z
    `modele_commita`: `model_agenta(nazwa, data)` daje model agenta ze stopki `Agent:` (`agenci.model_w_dniu`)."""
    przerwa = dt.timedelta(minutes=konf.get("pr_przerwa_rundy_min") or PRZERWA_RUNDY_MIN)
    pomin = tuple(POMIN_GALEZIE if konf.get("pr_pomin_galezie") is None else konf["pr_pomin_galezie"])
    maks = konf.get("pr_max_commitow") or MAX_COMMITOW
    wynik = []
    for p in lista:
        if (pomin and (p.get("galaz") or "").startswith(pomin)) or p["commitow"] > maks:
            continue
        wlasne = sorted((c for c in p["commity"] if not c["scalenie"] and not c["naglowek"].startswith("Merge ")),
                        key=lambda c: c["ts"])
        scalony, utworzony = tokeny.czas_lokalny(p["scalony"] or ""), tokeny.czas_lokalny(p["utworzony"] or "")
        if not wlasne or not scalony:
            continue
        rundy, poprzedni, rozbieznosc = [[]], None, False
        for c in wlasne:
            modele, rozb = modele_commita(c, model_agenta)
            c, rozbieznosc = dict(c, modele=modele), rozbieznosc or rozb
            czas = tokeny.czas_lokalny(c["ts"])
            if poprzedni and czas and czas - poprzedni > przerwa:
                rundy.append([])
            rundy[-1].append(c)
            poprzedni = czas or poprzedni
        autor = collections.Counter(m for c in rundy[0] for m in c["modele"]).most_common(1)
        autor = autor[0][0] if autor else None
        wynik.append({"repo": p.get("repo"), "pr": p["pr"], "scalony": scalony, "tydzien": tokeny.poniedzialek(scalony),
                      "autor": autor, "rundy": len(rundy) - 1, "commity": len(wlasne),
                      "poprawki": collections.Counter((autor, m) for r in rundy[1:] for c in r for m in c["modele"] or [None]),
                      "h": (scalony - utworzony).total_seconds() / 3600 if utworzony else None,
                      "linie": p.get("linie"), "pliki": p.get("pliki"), "rozbieznosc_modelu": rozbieznosc})
    return wynik


def opis_pr(lista: list) -> dict:
    if not lista:
        return {"pr": 0, "z_poprawka": None, "rundy": None, "commity": None, "h": None}
    godziny = [r["h"] for r in lista if r["h"] is not None]
    return {"pr": len(lista), "z_poprawka": round(100 * sum(r["rundy"] > 0 for r in lista) / len(lista), 1),
            "rundy": round(statistics.mean(r["rundy"] for r in lista), 2),
            "commity": round(statistics.mean(r["commity"] for r in lista), 1),
            "h": round(statistics.median(godziny), 1) if godziny else None}


def nazwa_modelu(m) -> str:
    return m or t("ef_bez_stopki")


# ---------------------------------------------------------------- powroty od przeglądu i CI (transkrypcje)

def powroty(dane: dict, wzorce: list, od, do):
    """Ze zdarzeń `zdarzenia_agentow.py`: {(typ, rodzina) implementatora: Counter} i Counter powrotów wg przyczyny
    (przeglad, ci). Powrót = implementator uruchomiony albo kontynuowany na tym samym PR (w tej samej sesji) po
    negatywnym werdykcie przeglądu albo czerwonym CI. Przegląd i CI idą do ostatniego implementatora tego PR."""
    agenci = dane.get("agenci") or {}
    stat, przyczyny = collections.defaultdict(collections.Counter), collections.Counter()
    ostatni, negatywne = {}, collections.defaultdict(set)
    bez_impl = (t("rola_sesja"), "")
    for e in sorted(dane.get("zdarzenia") or [], key=lambda e: (e.get("s") or "", e.get("ts") or "")):
        czas = tokeny.czas_lokalny(e.get("ts") or "")
        if not czas or not (od <= czas < do):
            continue
        a = agenci.get(e.get("agent") or "", {})
        typ = e.get("typ") or a.get("typ") or "?"
        model = rodzina(e.get("model") or a.get("model"))
        r = rola(True, typ, wzorce)
        klucze = [(e["s"], p) for p in (e.get("pr") or a.get("pr") or [])] or [(e["s"], None)]
        if e["rodzaj"] in ("start", "kontynuacja") and r == "implementacja":
            for k in klucze:
                if negatywne[k]:
                    stat[ostatni.get(k, (typ, model))]["powroty"] += 1
                    przyczyny.update(negatywne[k])
                    negatywne[k].clear()
                ostatni[k] = (typ, model)
            if e["rodzaj"] == "start":
                stat[(typ, model)]["uruchomienia"] += 1
        elif e["rodzaj"] == "raport":
            for k in klucze:
                impl = ostatni.get(k, bez_impl)
                if r == "przeglad" and e.get("werdykt"):
                    stat[impl]["przeglady"] += 1
                    if e["werdykt"] == "negatywny":
                        stat[impl]["przeglady_neg"] += 1
                        negatywne[k].add("przeglad")
                if r == "ci":
                    for pr, wynik in e.get("ci") or []:
                        if pr == k[1]:
                            stat[impl]["ci"] += 1
                            if wynik == "porazka":
                                stat[impl]["ci_porazki"] += 1
                                negatywne[k].add("ci")
    return stat, przyczyny


# ---------------------------------------------------------------- porównanie z poprzednimi retro

def liczba(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def poprzednie_wiersze(plik_csv: pathlib.Path, metryki: dict, n: int = POPRZEDNIE_RETRO):
    """Ostatnie `n` wierszy `metryki.csv` bez wiersza tego samego okna (gdy skrypt uruchomiono ponownie po dopisaniu
    metryk); None, gdy pliku nie ma."""
    try:
        with plik_csv.open(encoding="utf-8", newline="") as f:
            wiersze = list(csv.DictReader(f))
    except OSError:
        return None
    okno = lambda w: (w.get("okno_od") or "", w.get("okno_od_godzina") or "")  # noqa: E731
    return [w for w in wiersze if okno(w) != okno(metryki)][-n:]


def porownanie(plik_csv: pathlib.Path, metryki: dict, n: int = POPRZEDNIE_RETRO):
    """([etykiety poprzednich retro], [(metryka, [wartości], teraz, kierunek)]) z ostatnich `n` wierszy `metryki.csv`."""
    wiersze = poprzednie_wiersze(plik_csv, metryki, n)
    if wiersze is None:
        return [], []
    wynik = []
    for kol in POROWNANIE:
        wartosci = [liczba(w.get(kol)) for w in wiersze]
        teraz = liczba(metryki.get(kol))
        dostepne = [v for v in wartosci if v is not None]
        strz = tokeny.strzalka(statistics.median(dostepne), teraz) if dostepne else ""
        kierunek = {"↑": t("kier_gorzej"), "↓": t("kier_lepiej"), "≈": "≈"}.get(strz, "—")
        wynik.append((kol, wartosci, teraz, kierunek))
    return [w.get("retro") or "?" for w in wiersze], wynik


# ---------------------------------------------------------------- raport

def fmt(v) -> str:
    if v is None:
        return "—"
    if abs(v) >= 10000:
        return f"{v / 1000:.0f}k"
    return f"{v:g}" if v == int(v) or abs(v) >= 100 else f"{round(v, 2):g}"


def fmt_usd(v) -> str:
    return f"{v:.0f}" if v >= 10 else f"{v:.2f}"


def w_oknie(rundy, od, do) -> list:
    """PR scalone w oknie [od, do): jedyna definicja wiersza okna, tabel okna i `metryki.csv`."""
    return [r for r in rundy or [] if od <= r["scalony"] < do]


def tabela_konfiguracji_wiersze(polaczone: list, progi) -> list:
    """Tabela koszt i jakość na PR dla podanych PR, z liczbą PR bez przypisanej pracy agentów."""
    l = []
    grupy = tabela_konfiguracji(polaczone, progi)
    if not grupy:
        l.append(t("ef_konf_brak"))
    else:
        l += [t("ef_konf_kolumny"), "|---|---|---|---|---|---|---|---|---|"]
        kolejnosc = {"S": 0, "M": 1, "L": 2, "?": 3}
        for (konf, rozm), lista in sorted(grupy.items(), key=lambda x: (kolejnosc[x[0][1]], -len(x[1]), x[0][0])):
            o = opis_konfiguracji(lista)
            pr = f"{o['pr']}" if o["pr"] >= MIN_PR else f"{o['pr']}*"
            usd = lambda v: "—" if v is None else f"${v:.2f}"  # noqa: E731
            if konf == t("rola_sesja"):      # implementacja w sesji głównej: jej kosztu nie przypisujemy do PR
                o["impl"] = o["na_pr"] = o["na_100_linii"] = None
            l.append(f"| {konf} | {rozm} | {pr} | {o['z_poprawka']:g}% | {fmt(o['rundy'])} | {usd(o['impl'])} | "
                     f"{usd(o['kontrola'])} | **{usd(o['na_pr'])}** | {usd(o['na_100_linii'])} |")
    bez = sum(1 for r in polaczone if r["pr_koszt"] is None)
    if polaczone:
        l += ["", t("ef_konf_bez_kosztu", bez=bez, wszystkie=len(polaczone))]
    return l


def raport_konfiguracji(polaczone: list, agenci_konf: list, wzorce: list, progi=None, od=None, do=None) -> list:
    """Koszt i jakość na PR wg konfiguracji implementatora (model · poziom rozumowania) i rozmiaru PR, z kilku tygodni
    i osobno z samego okna retro (gdy podano `od`, `do`), oraz obecna konfiguracja agentów z `.claude/agents`."""
    progi = progi or PROGI_ROZMIARU
    l = ["", t("ef_konf_tytul"), "", t("ef_konf_opis", s=progi[0], m=progi[1], min_pr=MIN_PR), ""]
    l += tabela_konfiguracji_wiersze(polaczone, progi)
    if od is not None:
        l += ["", t("ef_konf_okno", od=f"{od:%m-%d %H:%M}", do=f"{do - dt.timedelta(days=1):%m-%d}"), ""]
        l += tabela_konfiguracji_wiersze(w_oknie(polaczone, od, do), progi)
    if agenci_konf:
        l += ["", t("ef_agenci_tytul"), "", t("ef_agenci_kolumny"), "|---|---|---|---|---|"]
        l += [f"| {nazwa} | {etykieta_roli(rola(True, nazwa, wzorce))} | {model} | {poziom or '—'} | {zrodlo} |"
              for nazwa, model, poziom, zrodlo in agenci_konf]
    return l


def ostrzezenia_repo(koszty: list, rundy, repozytoria: list, dzis: dt.date = None,
                     prog_usd: float = PROG_KOSZTU_TYGODNIA, od: dt.date = None) -> list:
    """Tygodnie o wysokim koszcie i małej liczbie PR w śledzonych repo: praca mogła przejść do repo spoza retro, a
    wtedy % z poprawką i koszt na PR opisują nie to repo. Tylko tygodnie od `od` (początek okna), żeby stary tydzień
    nie wracał w każdym retro. Bez danych z GitHuba (`rundy` None) nie ma ostrzeżeń."""
    if rundy is None:
        return []
    dzis = dzis or dt.date.today()
    sumy = collections.Counter()
    for _, _, s in koszty:
        sumy.update(s)
    if not sumy:
        return []
    pr = collections.Counter(r["tydzien"] for r in rundy)
    na_pr = {w: sumy[w] / pr[w] for w in sumy if pr[w]}
    wynik = []
    for w in sorted(sumy):
        if sumy[w] < prog_usd or (od and w + dt.timedelta(days=6) < od):
            continue
        inne = [v for x, v in na_pr.items() if x != w]
        if not pr[w] or (inne and na_pr[w] >= KROTNOSC_KOSZTU_NA_PR * statistics.median(inne)) \
                or (not inne and pr[w] < MIN_PR):
            wynik.append(t("ef_zmiana_repo", tydzien=w.isoformat() + (t("ef_niezak") if w + dt.timedelta(days=6) >= dzis else ""),
                           koszt=fmt_usd(sumy[w]), pr=pr[w], repo=", ".join(f"`{r}`" for r in repozytoria) or "—"))
    return wynik


def notka_zdarzen(nazwa: str, dane: dict, polaczone, od, do) -> str:
    """Data odczytu i ostatniego zdarzenia źródła zdalnego oraz ile PR okna nie ma implementatora, także dlatego, że
    scalono je po ostatnim zdarzeniu: zdarzenia kończą się w chwili odczytu, a metryka `pr_bez_agenta_proc` tego nie widzi."""
    pokaz = lambda c: f"{c:%Y-%m-%d %H:%M}" if c else "—"  # noqa: E731
    czasy = [tokeny.czas_lokalny(x.get("ts") or "") for x in (dane.get("zdarzenia") or [])]
    czasy += [tokeny.czas_lokalny(x.get("ts") or "") for x in (dane.get("agenci") or {}).values()]
    ostatnie = max((c for c in czasy if c), default=None)
    bez = [r for r in w_oknie(polaczone, od, do) if not r.get("pr_impl")]
    po = sum(1 for r in bez if ostatnie is None or r["scalony"] > ostatnie)
    return t("ef_zdarzenia_odczyt", nazwa=nazwa, ostatnie=pokaz(ostatnie),
             odczyt=pokaz(tokeny.czas_lokalny((dane.get("meta") or {}).get("odczyt_utc") or "")),
             bez=len(bez), wszystkie=len(w_oknie(polaczone, od, do)), po=po)


def okna_retro(plik_csv, metryki: dict, od, do, n: int = POPRZEDNIE_RETRO) -> list:
    """[(etykieta, od, do, chmura USD)] poprzednich retro z `metryki.csv` i okno bieżące na końcu. Okno kończy się
    najpóźniej tam, gdzie zaczyna się następne, żeby dzień retro nie liczył się dwa razy."""
    wiersze = poprzednie_wiersze(plik_csv, metryki, n) if plik_csv is not None else None
    wynik = []
    for w in wiersze or []:
        try:
            poczatek = dt.datetime.fromisoformat(f"{w.get('okno_od')}T{w.get('okno_od_godzina') or '00:00'}").astimezone()
            koniec = dt.datetime.combine(dt.date.fromisoformat(w.get("okno_do") or ""), dt.time()).astimezone()
        except (TypeError, ValueError):
            continue
        wynik.append([w.get("retro") or "?", poczatek, koniec + dt.timedelta(days=1), liczba(w.get("chmura_koszt_usd"))])
    wynik.append([t("ef_teraz"), od, do, liczba(metryki.get("chmura_koszt_usd"))])
    for a, b in zip(wynik, wynik[1:]):
        a[2] = min(a[2], b[1])
    return [tuple(w) for w in wynik]


def komorka_pr(lista: list, z_kosztem: bool = False) -> str:
    """„12 PR · 33% · 0.5” (PR, % z poprawką, rund na PR); „3* PR”, gdy próba mniejsza niż MIN_PR."""
    if not lista:
        return "—"
    o = opis_pr(lista)
    s = f"{o['pr']}{'' if o['pr'] >= MIN_PR else '*'} PR · {o['z_poprawka']:g}% · {fmt(o['rundy'])}"
    if z_kosztem:
        s += f" · ${opis_konfiguracji(lista)['na_pr']:.2f}"
    return s


def raport_wynikow(okna: list, rekordy: list, rundy, polaczone, od_tygodnia: dt.date, progi=None) -> list:
    """Tabela wyników do zamknięcia retro (krok 6): każde okno z `okna_retro` policzone dziś tą samą definicją, z
    archiwów kosztu (`rekordy`: [(źródło, `rekordy_kosztu`)]) i scalonych PR. Okno starsze niż początek tabel
    (`od_tygodnia`) nie ma danych PR („—”). Wartość z mniej niż MIN_PR PR ma gwiazdkę."""
    progi = progi or PROGI_ROZMIARU
    dane = []
    for _, od, do, _ in okna:
        wg_zrodla = {nazwa: [x for x in lista if od <= x["czas"] < do] for nazwa, lista in rekordy}
        wszystkie = [x for lista in wg_zrodla.values() for x in lista]
        pokryte = rundy is not None and od.date() >= od_tygodnia
        poziomy = collections.Counter()
        for x in wszystkie:
            poziomy[x["poziom"]] += x["koszt"]
        dane.append({"koszt": sum(x["koszt"] for x in wszystkie),
                     "wg_zrodla": {nazwa: sum(x["koszt"] for x in lista) for nazwa, lista in wg_zrodla.items()},
                     "tokeny": sum(x["tokeny"] for x in wszystkie), "bez_odczytu": sum(x["bez_odczytu"] for x in wszystkie),
                     "poziomy": poziomy, "pr": w_oknie(rundy, od, do) if pokryte else None,
                     "polaczone": w_oknie(polaczone, od, do) if pokryte and polaczone is not None else None})
    gw = lambda d: "" if d["pr"] is not None and len(d["pr"]) >= MIN_PR else "*"  # noqa: E731

    def wskaznik(d):
        """(koszt na scalony PR, % z poprawką, rund na PR) albo Nones, gdy okno nie ma PR."""
        if not d["pr"]:
            return None, None, None
        o = opis_pr(d["pr"])
        return d["koszt"] / o["pr"] if rekordy else None, o["z_poprawka"], o["rundy"]

    def kierunek(i):
        teraz = dane[-1]
        wartosc = wskaznik(teraz)[i]
        wczesniej = [wskaznik(d)[i] for d in dane[:-1] if d["pr"] and not gw(d)]
        if gw(teraz) or wartosc is None or not wczesniej:
            return "—"
        strz = tokeny.strzalka(statistics.median(wczesniej), wartosc)
        return {"↑": f"**{t('kier_gorzej')}**", "↓": t("kier_lepiej"), "≈": "≈"}.get(strz, "—")

    naglowki = [o[0] for o in okna]
    l = ["", t("ef_wyn_tytul"), "", t("ef_wyn_opis", min_pr=MIN_PR), "",
         f"| {t('ef_metryka')} | " + " | ".join(naglowki) + f" | {t('ef_wyn_kierunek')} |",
         "|---|" + "---|" * (len(okna) + 1)]

    def wiersz(etykieta, komorki, kier="—"):
        l.append(f"| {etykieta} | " + " | ".join(komorki) + f" | {kier} |")

    wiersz(t("ef_wyn_okno"), [f"{o[1]:%m-%d %H:%M} … {o[2] - dt.timedelta(minutes=1):%m-%d}" for o in okna])
    wiersz(t("ef_wyn_koszt"), [f"${d['koszt']:.0f}" if rekordy else "—" for d in dane])     # bez archiwów nieznany, nie 0
    if len(rekordy) > 1:
        for nazwa, _ in rekordy:
            wiersz(f"· `{nazwa}`", [f"${d['wg_zrodla'][nazwa]:.0f}" for d in dane])
    if any(o[3] is not None for o in okna):
        wiersz(t("ef_wyn_chmura"), ["—" if o[3] is None else f"${o[3]:.0f}" for o in okna])
    wiersz(t("ef_wyn_tokeny"), [f"{d['tokeny'] / 1e6:.1f}" if rekordy else "—" for d in dane])
    wiersz(t("ef_wyn_bez_odczytu"), [f"{d['bez_odczytu'] / 1e6:.1f}" if rekordy else "—" for d in dane])
    wiersz(t("ef_wyn_pr"), ["—" if d["pr"] is None else f"{len(d['pr'])}{gw(d)}" for d in dane])
    wiersz(t("ef_wyn_koszt_na_pr"), ["—" if wskaznik(d)[0] is None else f"${wskaznik(d)[0]:.2f}{gw(d)}" for d in dane],
           kierunek(0))
    wiersz(t("ef_wyn_z_poprawka"), ["—" if wskaznik(d)[1] is None else f"{wskaznik(d)[1]:g}%{gw(d)}" for d in dane],
           kierunek(1))
    wiersz(t("ef_wyn_rundy"), ["—" if wskaznik(d)[2] is None else f"{fmt(wskaznik(d)[2])}{gw(d)}" for d in dane],
           kierunek(2))

    def grupy(klucz, zrodlo, etykieta, kolejnosc=None, z_kosztem=False):
        """Wiersze podziału: PR okien pogrupowane wg `klucz`, od największej grupy w całej tabeli."""
        podzial = [collections.defaultdict(list) for _ in dane]
        for g, d in zip(podzial, dane):
            for r in d[zrodlo] or []:
                k = klucz(r)
                if k is not None:
                    g[k].append(r)
        licznik = collections.Counter({k: sum(len(g[k]) for g in podzial if k in g) for g in podzial for k in g})
        klucze = sorted(licznik, key=lambda k: kolejnosc.index(k)) if kolejnosc else [k for k, _ in licznik.most_common()]
        for k in klucze:
            wiersz(etykieta(k), [komorka_pr(g[k], z_kosztem) if k in g else "—" for g in podzial])

    grupy(lambda r: nazwa_modelu(r["autor"]), "pr", lambda k: t("ef_wyn_model", m=k))
    grupy(lambda r: rozmiar(r["linie"], progi), "pr", lambda k: t("ef_wyn_rozmiar", r=k), ["S", "M", "L", "?"])
    grupy(lambda r: konfiguracja(r["pr_impl"][1], r["pr_impl"][2]) if r["pr_impl"] and r["pr_koszt"] is not None else None,
          "polaczone", lambda k: t("ef_wyn_impl", k=k), z_kosztem=True)
    grupy(lambda r: None if r["pr_impl"] else t("ef_wyn_bez_impl"), "polaczone", lambda k: k)
    razem = [sum(d["poziomy"].values()) for d in dane]
    for poziom in sorted({p for d in dane for p in d["poziomy"]}, key=lambda p: (p is None, p or "")):
        wiersz(t("ef_wyn_poziom", p=poziom or t("ef_wyn_poziom_brak")),
               [f"${d['poziomy'][poziom]:.0f} ({100 * d['poziomy'][poziom] / r:.0f}%)" if r and d["poziomy"][poziom] >= 0.5
                else "—" for d, r in zip(dane, razem)])
    return l


def raport(porown, koszty: list, rundy: list, od, do, powroty_zrodel: list, uwagi: list, dzis: dt.date = None,
           przerwa: int = PRZERWA_RUNDY_MIN, polaczone: list = None, agenci_konf: list = (), wzorce: list = (),
           progi=None, okna_kosztu: dict = None, wyniki: list = ()) -> list:
    """Linie sekcji podsumowania. `koszty`: [(źródło, tab, sumy)]; `rundy`: rekordy `rundy_pr` z kilku tygodni
    (None = pominięte); `powroty_zrodel`: [(źródło, stat, przyczyny)]; `uwagi`: notatki o pominięciach;
    `polaczone`: `polacz_pr` (None = bez GitHuba); `agenci_konf`: `konfiguracja_agentow`; `okna_kosztu`: {źródło:
    `koszt_okna`} (kolumna okna w tabeli kosztu); `wyniki`: gotowe linie `raport_wynikow`."""
    dzis = dzis or dt.date.today()
    okna_kosztu = okna_kosztu or {}
    l = ["", t("ef_tytul"), "", t("ef_opis")]
    if uwagi:
        l += [""] + [f"- {u}" for u in uwagi]
    l += list(wyniki)
    # 1. porównanie z poprzednimi retro
    etykiety, wiersze = porown
    l += ["", t("ef_porownanie"), ""]
    if not etykiety:
        l.append(t("ef_porownanie_brak"))
    else:
        l += ["| " + t("ef_metryka") + " | " + " | ".join(etykiety) + " | " + t("ef_teraz") + " | "
              + t("ef_kierunek") + " |", "|---|" + "---|" * (len(etykiety) + 2)]
        for kol, wartosci, teraz, kierunek in wiersze:
            kier = f"**{kierunek}**" if kierunek.startswith("↑") else kierunek
            l.append(f"| {kol} | " + " | ".join(fmt(v) for v in wartosci) + f" | {fmt(teraz)} | {kier} |")
    # 2. koszt wg roli i modelu
    for zrodlo, tab, sumy in koszty:
        tygodnie = sorted(sumy)
        if not tygodnie:
            continue
        l += ["", t("ef_koszt_rol", zrodlo=zrodlo), ""]
        naglowki = [tydz.isoformat()[5:] + (t("ef_niezak") if tydz + dt.timedelta(days=6) >= dzis else "")
                    for tydz in tygodnie]
        okno = okna_kosztu.get(zrodlo, collections.Counter())
        okno_razem = sum(okno.values())
        kol_okna = [f"**{t('ef_okno')}**"] if zrodlo in okna_kosztu else []
        l += ["| " + t("ef_rola_model") + " | " + " | ".join(naglowki + kol_okna) + " |",
              "|---|" + "---|" * (len(tygodnie) + len(kol_okna))]
        klucze = sorted({k[1:] for k in tab} | set(okno), key=lambda x: -sum(tab[(w, *x)] for w in tygodnie))
        for r, m, poziom in klucze:
            komorki = [f"{fmt_usd(tab[(w, r, m, poziom)])} ({100 * tab[(w, r, m, poziom)] / sumy[w]:.0f}%)"
                       if tab[(w, r, m, poziom)] >= 0.01 and sumy[w] else "—" for w in tygodnie]
            if kol_okna:
                k = okno[(r, m, poziom)]
                komorki.append(f"{fmt_usd(k)} ({100 * k / okno_razem:.0f}%)" if k >= 0.01 else "—")
            l.append(f"| {etykieta_roli(r)} · {konfiguracja(m, poziom)} | " + " | ".join(komorki) + " |")
        l.append(f"| **{t('ef_razem')}** | " + " | ".join(
            [f"**{fmt_usd(sumy[w])}**" for w in tygodnie] + ([f"**{fmt_usd(okno_razem)}**"] if kol_okna else [])) + " |")
    # 3. rundy poprawek w scalonych PR
    if rundy is not None:
        l += ["", t("ef_rundy"), "", t("ef_rundy_opis", przerwa=przerwa)]
        kolumny = "| " + " | ".join(t(k) for k in ("ef_pr", "ef_z_poprawka", "ef_rund_na_pr", "ef_commitow_na_pr",
                                                    "ef_mediana_h")) + " |"
        tygodnie = collections.defaultdict(list)
        modele = collections.defaultdict(list)
        for r in rundy:
            tygodnie[r["tydzien"]].append(r)
            modele[r["autor"]].append(r)
        okno_pr = w_oknie(rundy, od, do)

        def wiersz(etykieta, lista):
            o = opis_pr(lista)
            proc = "—" if o["z_poprawka"] is None else f"{o['z_poprawka']:g}%"
            return f"| {etykieta} | {o['pr']} | {proc} | {fmt(o['rundy'])} | {fmt(o['commity'])} | {fmt(o['h'])} |"

        l += ["", f"| {t('ef_tydzien_scalenia')} " + kolumny, "|---|---|---|---|---|---|"]
        l += [wiersz(tydz.isoformat() + (t("ef_niezak") if tydz + dt.timedelta(days=6) >= dzis else ""), tygodnie[tydz])
              for tydz in sorted(tygodnie)]
        l.append(wiersz(f"**{t('ef_okno')}**", okno_pr))
        tyg_okna = collections.Counter(r["tydzien"] for r in okno_pr)
        if len(tyg_okna) > 1:
            l += ["", t("ef_okno_tygodnie", od=f"{od:%m-%d %H:%M}", podzial=", ".join(
                f"{tydz.isoformat()[5:]}: {n}" for tydz, n in sorted(tyg_okna.items())))]
        l += ["", f"| {t('ef_model_autora')} " + kolumny, "|---|---|---|---|---|---|"]
        l += [wiersz(nazwa_modelu(m), lista) for m, lista in sorted(modele.items(), key=lambda x: -len(x[1]))]
        nazwy = sorted(modele, key=lambda m: -len(modele[m]))
        if len(nazwy) > 1:
            l += ["", "| " + t("ef_tydzien") + " | " + " | ".join(nazwa_modelu(m) for m in nazwy) + " |",
                  "|---|" + "---|" * len(nazwy)]
            for tydz in sorted(tygodnie):
                komorki = []
                for m in nazwy:
                    lista = [r for r in tygodnie[tydz] if r["autor"] == m]
                    o = opis_pr(lista)
                    komorki.append(t("ef_komorka", pr=o["pr"], proc=f"{o['z_poprawka']:g}") if lista else "—")
                l.append(f"| {tydz.isoformat()} | " + " | ".join(komorki) + " |")
        kto = collections.Counter()
        for r in rundy:
            kto.update(r["poprawki"])
        if kto:
            l += ["", t("ef_kto_poprawia") + ", ".join(f"{nazwa_modelu(a)} → {nazwa_modelu(b)}: {n}"
                                                       for (a, b), n in kto.most_common()) + "."]
    if polaczone is not None or agenci_konf:
        l += raport_konfiguracji(polaczone or [], agenci_konf, list(wzorce), progi,
                                 od if polaczone is not None else None, do)
    # 4. powroty w transkrypcjach
    for zrodlo, stat, przyczyny in powroty_zrodel:
        l += ["", t("ef_powroty", zrodlo=zrodlo), ""]
        if not stat:
            l.append(t("ef_powroty_brak"))
            continue
        l += [t("ef_powroty_opis"), "", t("ef_powroty_kolumny"), "|---|---|---|---|---|"]
        for (typ, model), s in sorted(stat.items(), key=lambda x: -sum(x[1].values())):
            l.append(f"| {typ}{' · ' + model if model else ''} | {s['uruchomienia']} | {s['przeglady']} ({s['przeglady_neg']}) | "
                     f"{s['ci']} ({s['ci_porazki']}) | {s['powroty']} |")
        l += ["", t("ef_powroty_przyczyny", przeglad=przyczyny["przeglad"], ci=przyczyny["ci"])]
    l += ["", t("ef_ograniczenia")]
    return l


def metryki_okna(rundy, od, do, powroty_zrodel: list, wywolania: list, wzorce: list, polaczone: list = None) -> dict:
    """Kolumny `metryki.csv` od 0.3.0 i 0.4.0 (PR scalone w oknie; powroty ze wszystkich źródeł)."""
    okno_pr = w_oknie(rundy, od, do) if rundy is not None else None
    m = {"pr_analizowane": None, "pr_z_poprawka_proc": None, "rundy_na_pr": None, "pr_wg_modelu": None,
         "pr_z_poprawka_proc_wg_modelu": None}
    if okno_pr is not None:
        o = opis_pr(okno_pr)
        modele = collections.defaultdict(list)
        for r in okno_pr:
            modele[nazwa_modelu(r["autor"])].append(r)
        m.update({"pr_analizowane": o["pr"], "pr_z_poprawka_proc": o["z_poprawka"], "rundy_na_pr": o["rundy"],
                  "pr_wg_modelu": udzialy(collections.Counter({k: len(v) for k, v in modele.items()})),
                  "pr_z_poprawka_proc_wg_modelu": ";".join(
                      f"{k}:{opis_pr(v)['z_poprawka']:g}" for k, v in sorted(modele.items(), key=lambda x: -len(x[1])))
                  or None})
    przyczyny = collections.Counter()
    for _, _, p in powroty_zrodel:
        przyczyny.update(p)
    m["powroty_przeglad"] = przyczyny["przeglad"] if powroty_zrodel else None
    m["powroty_ci"] = przyczyny["ci"] if powroty_zrodel else None
    m["koszt_implementacji_proc_wg_modelu"] = koszt_implementacji_wg_modelu(wywolania, wzorce)
    # od 0.4.0: koszt agentów na PR scalony w oknie i wg konfiguracji implementatora, udział poziomów rozumowania
    z_kosztem = [r for r in w_oknie(polaczone, od, do) if r["pr_koszt"] is not None and r["pr_impl"]]
    m["pr_powiazane"] = len(z_kosztem) if polaczone is not None else None
    m["koszt_na_pr_usd"] = round(opis_konfiguracji(z_kosztem)["na_pr"], 2) if z_kosztem else None
    grupy = collections.defaultdict(list)
    for (konf, _), lista in tabela_konfiguracji(z_kosztem).items():
        grupy[konf.replace(" · ", "/")] += lista
    m["koszt_na_pr_wg_konfiguracji"] = ";".join(
        f"{k}:{opis_konfiguracji(v)['na_pr']:.2f}" for k, v in sorted(grupy.items(), key=lambda x: -len(x[1]))) or None
    m["koszt_wg_poziomu"] = koszt_wg_poziomu(wywolania)
    return m
