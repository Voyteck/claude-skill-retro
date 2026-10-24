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
POROWNANIE = ["koszt_na_wiadomosc_usd", "kontekst_mediana", "kontekst_ponad_200k_proc", "kontekst_startowy_mediana",
              "podagenci_opus_koszt_proc", "wybudzenia_koszt_usd", "pr_z_poprawka_proc", "rundy_na_pr",
              "powroty_przeglad", "powroty_ci", "koszt_na_pr_usd"]
POPRZEDNIE_RETRO = 3
# Rozmiar PR (dodane + usunięte linie): S do pierwszego progu, M do drugiego, L powyżej.
PROGI_ROZMIARU = [50, 300]
# Konfiguracja implementatora ma wynik, a nie tylko wskazówkę, od tylu PR w komórce tabeli.
MIN_PR = 5
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
    for r in calls.values():
        w = tokeny.z_rekordu(r)
        if not w["czas"]:
            continue
        tydz = tokeny.poniedzialek(w["czas"])
        if tydz < od_tygodnia:
            continue
        c = tokeny.czesci_kosztu(w, cennik, tokeny.model_biezacy(w["model"], cennik))
        if not c:
            continue
        k = sum(c.values())
        tab[(tydz, rola(r.get("sub"), r.get("agent"), wzorce), rodzina(w["model"]), w.get("effort"))] += k
        sumy[tydz] += k
    return tab, sumy


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
    implementatora albo None}} ze zdarzeń agentów. `zrodla`: [(dane `zdarzenia_agentow`, {sesja: repo})].
    Koszt agenta, który pracował nad kilkoma PR, dzieli się po równo."""
    wynik = collections.defaultdict(lambda: {"koszt": collections.Counter(), "impl": None})
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
        koszt, impl = collections.Counter(), None
        for rek in reki:
            koszt.update(rek["koszt"])
            if rek["impl"] and (impl is None or rek["impl"][3] < impl[3]):
                impl = rek["impl"]
        wynik.append(dict(r, pr_koszt=koszt if reki else None, pr_impl=impl))
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
    """[(nazwa, model, poziom, źródło)] z nagłówków `.claude/agents/*.md` (pola `name`, `model`, `effort`)."""
    wynik = []
    for zrodlo, katalog in katalogi:
        for plik in sorted(pathlib.Path(katalog).glob("*.md")):
            try:
                linie = plik.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            if not linie or linie[0].strip() != "---":
                continue
            pola = {}
            for linia in linie[1:]:
                if linia.strip() == "---":
                    break
                m = re.match(r"(name|model|effort)\s*:\s*(.+)", linia)
                if m:
                    pola[m.group(1)] = m.group(2).strip().strip("'\"")
            wynik.append((pola.get("name") or plik.stem, pola.get("model") or "inherit", pola.get("effort"), zrodlo))
    return wynik


# ---------------------------------------------------------------- rundy poprawek w scalonych PR

def _uruchom(polecenie, cwd=None):
    try:
        r = subprocess.run(polecenie, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=180)
        return r.returncode, r.stdout, r.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, "", str(e)


def pr_commity(sciezka: str, od_data: dt.date, do_data: dt.date, gh: str):
    """Scalone PR repo z commitami (data autorstwa, nagłówek, modele ze stopek `Co-Authored-By: Claude <Model>`):
    (lista, None) albo (None, błąd). `gh api graphql` z wyszukiwaniem po 40, bo `gh pr list --json commits`
    przekracza limit węzłów GraphQL."""
    kod, out, err = _uruchom([gh, "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"], sciezka)
    if kod != 0 or not out.strip():
        return None, (err or out).strip()[:160] or "gh repo view"
    repo, wynik, po = out.strip(), [], None
    for _ in range(MAX_STRON_GH):
        arg = [gh, "api", "graphql", "-f", "query=" + ZAPYTANIE_PR,
               "-f", f"q=repo:{repo} is:pr is:merged merged:{od_data.isoformat()}..{do_data.isoformat()}"]
        if po:
            arg += ["-f", "po=" + po]
        kod, out, err = _uruchom(arg, sciezka)
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
                        "modele": sorted({rodzina(m) for m in WZOR_MODELU.findall(c["commit"].get("messageBody") or "")})}
                       for c in n["commits"]["nodes"]]
            wynik.append({"repo": repo, "pr": n["number"], "utworzony": n["createdAt"], "scalony": n["mergedAt"],
                          "galaz": n["headRefName"], "commitow": n["commits"]["totalCount"], "commity": commity,
                          "linie": (n.get("additions") or 0) + (n.get("deletions") or 0), "pliki": n.get("changedFiles")})
        if not s["pageInfo"]["hasNextPage"]:
            break
        po = s["pageInfo"]["endCursor"]
    return wynik, None


def rundy_pr(lista: list, konf: dict) -> list:
    """Rundy poprawek każdego PR: paczka commitów po przerwie > `pr_przerwa_rundy_min` to runda; pierwsza paczka to
    praca, kolejne to powroty. Model autora = najczęstsza stopka w pierwszej paczce (None = bez stopki)."""
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
        rundy, poprzedni = [[]], None
        for c in wlasne:
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
                      "linie": p.get("linie"), "pliki": p.get("pliki")})
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


def porownanie(plik_csv: pathlib.Path, metryki: dict, n: int = POPRZEDNIE_RETRO):
    """([etykiety poprzednich retro], [(metryka, [wartości], teraz, kierunek)]) z ostatnich `n` wierszy `metryki.csv`
    (bez wiersza tego samego okna, gdy skrypt uruchomiono ponownie po dopisaniu metryk)."""
    try:
        with plik_csv.open(encoding="utf-8", newline="") as f:
            wiersze = list(csv.DictReader(f))
    except OSError:
        return [], []
    okno = lambda w: (w.get("okno_od") or "", w.get("okno_od_godzina") or "")  # noqa: E731
    wiersze = [w for w in wiersze if okno(w) != okno(metryki)][-n:]
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


def raport_konfiguracji(polaczone: list, agenci_konf: list, wzorce: list, progi=None) -> list:
    """Koszt i jakość na PR wg konfiguracji implementatora (model · poziom rozumowania) i rozmiaru PR oraz obecna
    konfiguracja agentów z `.claude/agents`."""
    progi = progi or PROGI_ROZMIARU
    l = ["", t("ef_konf_tytul"), "", t("ef_konf_opis", s=progi[0], m=progi[1], min_pr=MIN_PR), ""]
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
    if agenci_konf:
        l += ["", t("ef_agenci_tytul"), "", t("ef_agenci_kolumny"), "|---|---|---|---|---|"]
        l += [f"| {nazwa} | {etykieta_roli(rola(True, nazwa, wzorce))} | {model} | {poziom or '—'} | {zrodlo} |"
              for nazwa, model, poziom, zrodlo in agenci_konf]
    return l


def raport(porown, koszty: list, rundy: list, od, do, powroty_zrodel: list, uwagi: list, dzis: dt.date = None,
           przerwa: int = PRZERWA_RUNDY_MIN, polaczone: list = None, agenci_konf: list = (), wzorce: list = (),
           progi=None) -> list:
    """Linie sekcji podsumowania. `koszty`: [(źródło, tab, sumy)]; `rundy`: rekordy `rundy_pr` z kilku tygodni
    (None = pominięte); `powroty_zrodel`: [(źródło, stat, przyczyny)]; `uwagi`: notatki o pominięciach;
    `polaczone`: `polacz_pr` (None = bez GitHuba); `agenci_konf`: `konfiguracja_agentow`."""
    dzis = dzis or dt.date.today()
    l = ["", t("ef_tytul"), "", t("ef_opis")]
    if uwagi:
        l += [""] + [f"- {u}" for u in uwagi]
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
        l += ["| " + t("ef_rola_model") + " | " + " | ".join(naglowki) + " |", "|---|" + "---|" * len(tygodnie)]
        klucze = sorted({k[1:] for k in tab}, key=lambda x: -sum(tab[(w, *x)] for w in tygodnie))
        for r, m, poziom in klucze:
            komorki = [f"{fmt_usd(tab[(w, r, m, poziom)])} ({100 * tab[(w, r, m, poziom)] / sumy[w]:.0f}%)"
                       if tab[(w, r, m, poziom)] >= 0.01 and sumy[w] else "—" for w in tygodnie]
            l.append(f"| {etykieta_roli(r)} · {konfiguracja(m, poziom)} | " + " | ".join(komorki) + " |")
        l.append(f"| **{t('ef_razem')}** | " + " | ".join(f"**{fmt_usd(sumy[w])}**" for w in tygodnie) + " |")
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
        w_oknie = [r for r in rundy if od <= r["scalony"] < do]

        def wiersz(etykieta, lista):
            o = opis_pr(lista)
            proc = "—" if o["z_poprawka"] is None else f"{o['z_poprawka']:g}%"
            return f"| {etykieta} | {o['pr']} | {proc} | {fmt(o['rundy'])} | {fmt(o['commity'])} | {fmt(o['h'])} |"

        l += ["", f"| {t('ef_tydzien_scalenia')} " + kolumny, "|---|---|---|---|---|---|"]
        l += [wiersz(tydz.isoformat() + (t("ef_niezak") if tydz + dt.timedelta(days=6) >= dzis else ""), tygodnie[tydz])
              for tydz in sorted(tygodnie)]
        l.append(wiersz(f"**{t('ef_okno')}**", w_oknie))
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
        l += raport_konfiguracji(polaczone or [], agenci_konf, list(wzorce), progi)
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
    w_oknie = [r for r in rundy if od <= r["scalony"] < do] if rundy is not None else None
    m = {"pr_analizowane": None, "pr_z_poprawka_proc": None, "rundy_na_pr": None, "pr_wg_modelu": None,
         "pr_z_poprawka_proc_wg_modelu": None}
    if w_oknie is not None:
        o = opis_pr(w_oknie)
        modele = collections.defaultdict(list)
        for r in w_oknie:
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
    z_kosztem = [r for r in polaczone or [] if r["pr_koszt"] is not None and r["pr_impl"] and od <= r["scalony"] < do]
    m["pr_powiazane"] = len(z_kosztem) if polaczone is not None else None
    m["koszt_na_pr_usd"] = round(opis_konfiguracji(z_kosztem)["na_pr"], 2) if z_kosztem else None
    grupy = collections.defaultdict(list)
    for (konf, _), lista in tabela_konfiguracji(z_kosztem).items():
        grupy[konf.replace(" · ", "/")] += lista
    m["koszt_na_pr_wg_konfiguracji"] = ";".join(
        f"{k}:{opis_konfiguracji(v)['na_pr']:.2f}" for k, v in sorted(grupy.items(), key=lambda x: -len(x[1]))) or None
    m["koszt_wg_poziomu"] = koszt_wg_poziomu(wywolania)
    return m
