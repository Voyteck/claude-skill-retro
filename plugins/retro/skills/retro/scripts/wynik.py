"""Miary wyniku pracy (od 0.9.0): akceptacja scalonych PR, koszt zaakceptowanej zmiany, szczelność weryfikacji.

Retro do 0.8.x mierzy proces przed scaleniem (rundy poprawek, powroty od przeglądu i CI). Tu: co stało się z kodem
po scaleniu. Liczone dla kohorty PR scalonych 30–60 dni przed końcem okna (`wynik_dni`), bo z ostatnich 30 dni
nie wiadomo jeszcze, czy zmiana wróci do poprawki. Źródła: GitHub (`efektywnosc.pr_commity`: tytuł, opis, pliki,
commit scalenia), lokalny klon (`git blame` pod poprawką), zdarzenia agentów (werdykty przeglądu) i czasy wiadomości
właściciela. Bez nowych danych od użytkownika.

1. Akceptacja: PR bez rundy poprawki, którego w ciągu `wynik_dni` nie poprawił późniejszy PR (odwołanie
   „fixes/follow-up/revert/popraw… #N” albo PR typu poprawka zmieniający linie tego PR: `git blame` rodzica
   commita scalenia poprawki trafia w commity PR albo jego commit scalenia).
2. Koszt zaakceptowanej zmiany: koszt okna kohorty ze wszystkich źródeł / zaakceptowane PR kohorty; obok wiadomości
   właściciela i szacunek czasu uwagi (suma odstępów ≤ `wynik_uwaga_przerwa_min` między kolejnymi wiadomościami).
3. Szczelność weryfikacji: błędy złapane przez przegląd agentowy (powrót implementatora po negatywnym werdykcie) /
   wszystkie złapane (+ powrót implementatora po pozytywnym werdykcie: poprawka po akceptacji przeglądu, zwykle na
   polecenie właściciela; + poprawka produkcyjna: przeróbka z punktu 1 scalona do `wynik_hotfix_h` godzin po scaleniu,
   scalenie jako przybliżenie deployu). Poprawka trafiająca blame w więcej niż `wynik_zamiatanie_pr` PR to zamiatanie.

Ograniczenia: `references/sygnaly.md`, sekcja „Outcome measures”.
"""
import collections
import datetime as dt
import pathlib
import re
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import efektywnosc as ef  # noqa: E402
import tokeny  # noqa: E402
from teksty import t  # noqa: E402

DNI, HOTFIX_H, PRZERWA_UWAGI_MIN = 30, 48, 15
# Pliki synchronizowanych kopii reguł: zmieniają się seriami w wielu repo, nie są poprawką kodu.
POMIN_SCIEZKI = ["CLAUDE.md", "AGENTS.md", "docs/"]
MAX_ZAKRESOW_BLAME = 300
# Poprawka, której blame trafia w linie więcej niż tylu różnych PR, to zamiatanie (podbicie zależności, usunięcie
# kodu, przeniesienie), nie przeróbka konkretnej zmiany: blame pomijany, odwołania zostają.
ZAMIATANIE_PR = 3
WZOR_POPRAWKI = re.compile(r"^\W*(?:fix|hotfix|bugfix|revert|popraw|napraw)", re.I)
WZOR_ODWOLANIA = re.compile(r"(?<![\w/])#(\d{1,6})\b|/pull/(\d{1,6})\b")
WZOR_ODWOLANIA_POPRAWKI = re.compile(
    r"(?:\bfix(?:es|ed)?|\bhotfix|\brevert(?:s|ed)?|\bfollow[- ]?up|\bpopraw\w*|\bnapraw\w*)"
    r"(?:\s+(?:to|of|for|do))?\W{0,12}(?:PR\s*)?(?:#|https://\S+/pull/)(\d{1,6})\b", re.I)
WZOR_HUNKA = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@")


# ---------------------------------------------------------------- dane PR

def odwolania(tytul: str, opis: str) -> tuple:
    """({numery wspomniane}, {numery wspomniane jako poprawiane: fixes/follow-up/revert/popraw… #N})."""
    tekst = f"{tytul or ''}\n{opis or ''}"
    wszystkie = {int(a or b) for a, b in WZOR_ODWOLANIA.findall(tekst)}
    return wszystkie, {int(x) for x in WZOR_ODWOLANIA_POPRAWKI.findall(tekst)}


def czy_poprawka(r: dict) -> bool:
    """PR typu poprawka: tytuł `fix…`, `hotfix`, `revert`, `popraw…`, `napraw…` (także `fix(zakres):`)."""
    return bool(WZOR_POPRAWKI.match(r.get("tytul") or ""))


def pominieta(sciezka: str, pomin) -> bool:
    for p in pomin:
        if p.endswith("/") and (sciezka.startswith(p) or f"/{p}" in f"/{sciezka}"):
            return True
        if not p.endswith("/") and (sciezka == p or sciezka.endswith("/" + p)):
            return True
    return False


def blame_poprawki(sciezka_repo: str, oid: str, pomin, uruchom=None):
    """Commity, których linie zmienia (usuwa albo podmienia) commit `oid`: `git diff -U0 oid^1 oid`, potem
    `git blame -L` na rodzicu. None, gdy commitu nie ma w lokalnym klonie (trzeba `git fetch`)."""
    uruchom = uruchom or ef._uruchom
    kod, _, _ = uruchom(["git", "cat-file", "-e", f"{oid}^{{commit}}"], sciezka_repo)
    if kod != 0:
        return None
    kod, out, _ = uruchom(["git", "diff", "-U0", "--no-color", "--no-renames", "--no-ext-diff", f"{oid}^1", oid],
                          sciezka_repo)
    if kod != 0:
        return None
    zakresy, plik = collections.defaultdict(list), None
    for linia in out.splitlines():
        if linia.startswith("--- "):
            plik = linia[6:] if linia.startswith("--- a/") else None
        elif linia.startswith("@@") and plik and not pominieta(plik, pomin):
            m = WZOR_HUNKA.match(linia)
            if m and (m.group(2) is None or int(m.group(2)) > 0):
                zakresy[plik].append((int(m.group(1)), int(m.group(2) or 1)))
    wynik, n = set(), 0
    for plik, lista in zakresy.items():
        lista = lista[:max(0, MAX_ZAKRESOW_BLAME - n)]
        n += len(lista)
        if not lista:
            break
        arg = ["git", "blame", "--porcelain"]
        for poczatek, dlugosc in lista:
            arg += ["-L", f"{poczatek},+{dlugosc}"]
        kod, out, _ = uruchom(arg + [f"{oid}^1", "--", plik], sciezka_repo)
        if kod == 0:
            wynik.update(m.group(0) for m in re.finditer(r"^[0-9a-f]{40}(?= \d+ \d+)", out, re.M))
    return wynik


# ---------------------------------------------------------------- weryfikacja w zdarzeniach agentów

def weryfikacja_pr(zrodla: list, wzorce: list) -> dict:
    """{(repo albo None, nr PR): {"zlapane", "po_akceptacji", "recenzent": (model, poziom) | None}} ze zdarzeń
    agentów (`zrodla`: [(dane `zdarzenia_agentow`, {sesja: repo})], jak `efektywnosc.koszty_pr`). Złapane = powrót
    implementatora po negatywnym werdykcie przeglądu; po akceptacji = powrót po pozytywnym werdykcie bez czerwonego
    CI pomiędzy. Recenzent = ostatni agent przeglądu z werdyktem."""
    wynik = collections.defaultdict(lambda: {"zlapane": 0, "po_akceptacji": 0, "recenzent": None, "_ts": ""})
    for dane, repo_sesji in zrodla:
        agenci = dane.get("agenci") or {}
        stan = {}
        for e in sorted(dane.get("zdarzenia") or [], key=lambda e: (e.get("s") or "", e.get("ts") or "")):
            a = agenci.get(e.get("agent") or "", {})
            r = ef.rola(True, e.get("typ") or a.get("typ"), wzorce)
            repo = repo_sesji.get(e.get("s"))
            for pr in e.get("pr") or a.get("pr") or []:
                k, rek = (e.get("s"), pr), wynik[(repo, pr)]
                if e.get("rodzaj") in ("start", "kontynuacja") and r == "implementacja":
                    if stan.get(k) == "neg":
                        rek["zlapane"] += 1
                    elif stan.get(k) == "poz":
                        rek["po_akceptacji"] += 1
                    stan[k] = None
                elif e.get("rodzaj") == "raport" and r == "przeglad" and e.get("werdykt"):
                    stan[k] = "neg" if e["werdykt"] == "negatywny" else "poz"
                    if (e.get("ts") or "") >= rek["_ts"]:
                        poziom = (a.get("tokeny") or {}).get("eff") or a.get("effort_zadany") or e.get("effort_zadany")
                        rek["recenzent"], rek["_ts"] = (e.get("model") or a.get("model"), poziom), e.get("ts") or ""
                elif e.get("rodzaj") == "raport" and r == "ci":
                    if any(p == pr and w == "porazka" for p, w in e.get("ci") or []):
                        stan[k] = "ci"
    return {k: {x: v for x, v in rek.items() if x != "_ts"} for k, rek in wynik.items()}


def dopasuj(rekordy: list, slownik: dict) -> list:
    """Dla każdego rekordu PR wpis słownika {(repo, nr): …} albo None. Klucz bez repo (źródło zdalne) pasuje po
    numerze, gdy numer jest jednoznaczny wśród rekordów (jak `efektywnosc.polacz_pr`)."""
    numery = collections.Counter(r["pr"] for r in rekordy)
    wynik = []
    for r in rekordy:
        trafienia = [slownik[k] for k in ((r["repo"], r["pr"]), (None, r["pr"]))
                     if k in slownik and (k[0] is not None or numery[r["pr"]] == 1)]
        if not trafienia:
            wynik.append(None)
            continue
        suma = {"zlapane": sum(v["zlapane"] for v in trafienia), "po_akceptacji": sum(v["po_akceptacji"] for v in trafienia),
                "recenzent": next((v["recenzent"] for v in trafienia if v["recenzent"]), None)}
        wynik.append(suma)
    return wynik


# ---------------------------------------------------------------- kohorta

def okno_kohorty(koniec: dt.datetime, dni: int = DNI) -> tuple:
    """[koniec − 2·dni, koniec − dni): PR scalone w tym czasie miały pełne `dni` na powrót do poprawki."""
    return koniec - dt.timedelta(days=2 * dni), koniec - dt.timedelta(days=dni)


def ocena(wszystkie: list, od, do, repo_sciezki: dict, weryf: dict, konf: dict = None, cache: dict = None,
          uruchom=None) -> dict:
    """Ocena kohorty PR scalonych w [od, do). `wszystkie`: rekordy `efektywnosc.polacz_pr` z polami `tytul`,
    `odwolania`, `odwolania_poprawki`, `oid`, `oidy`, `sciezki` (od 0.9.0) z okresu od `od` do dziś;
    `repo_sciezki`: {właściciel/repo: lokalny klon}; `weryf`: `weryfikacja_pr`; `cache`: wyniki blame między
    wywołaniami. Zwraca {"pr": [rekord + wynik], "blame": Counter(ok, brak_klonu, brak_commita)}."""
    konf = konf or {}
    dni = int(konf.get("wynik_dni") or DNI)
    hotfix = dt.timedelta(hours=int(konf.get("wynik_hotfix_h") or HOTFIX_H))
    pomin = POMIN_SCIEZKI if konf.get("wynik_pomin_sciezki") is None else konf["wynik_pomin_sciezki"]
    cache = {} if cache is None else cache
    kohorta = [r for r in wszystkie if od <= r["scalony"] < do]
    wg_repo = collections.defaultdict(list)
    for r in wszystkie:
        wg_repo[r["repo"]].append(r)
    sprawdzone, zamiecione, zamiatanie = set(), set(), int(ZAMIATANIE_PR if konf.get("wynik_zamiatanie_pr") is None else konf["wynik_zamiatanie_pr"])
    autor_oid = collections.defaultdict(set)          # (repo, oid) → PR, których to commit albo commit scalenia
    for r in wszystkie:
        for oid in (r.get("oidy") or []) + ([r["oid"]] if r.get("oid") else []):
            autor_oid[(r["repo"], oid)].add(r["pr"])
    weryfikacja = dict(zip([(r["repo"], r["pr"]) for r in kohorta], dopasuj(kohorta, weryf)))

    def oidy_pod(q):
        klucz = (q["repo"], q["pr"])
        sprawdzone.add(klucz)
        if klucz not in cache:
            sciezka = repo_sciezki.get(q["repo"])
            if not sciezka or not q.get("oid"):
                cache[klucz] = "brak_klonu"
            else:
                wynik = blame_poprawki(sciezka, q["oid"], pomin, uruchom)
                cache[klucz] = "brak_commita" if wynik is None else wynik
        pod = cache[klucz]
        if not isinstance(pod, str):
            trafione = {n for oid in pod for n in autor_oid.get((q["repo"], oid), ())} - {q["pr"]}
            if len(trafione) > zamiatanie:
                zamiecione.add(klucz)
                return "zamiatanie"
        return pod

    wynik = []
    for p in kohorta:
        wlasne = set(p.get("oidy") or []) | ({p["oid"]} if p.get("oid") else set())
        przerobki, produkcja = [], []
        for q in wg_repo[p["repo"]]:
            if q is p or not (p["scalony"] < q["scalony"] <= p["scalony"] + dt.timedelta(days=dni)):
                continue
            sposob = None
            if p["pr"] in (q.get("odwolania_poprawki") or ()):
                sposob = "odwolanie"
            elif czy_poprawka(q):
                if p["pr"] in (q.get("odwolania") or ()):
                    sposob = "odwolanie"
                else:
                    pod = oidy_pod(q)
                    if not isinstance(pod, str) and pod & wlasne:
                        sposob = "blame"
            if sposob:
                przerobki.append((q["pr"], sposob))
                if q["scalony"] <= p["scalony"] + hotfix:
                    produkcja.append(q["pr"])
        w = weryfikacja.get((p["repo"], p["pr"])) or {"zlapane": 0, "po_akceptacji": 0, "recenzent": None}
        wynik.append(dict(p, przerobki=przerobki, produkcja=produkcja, zaakceptowany=p["rundy"] == 0 and not przerobki,
                          zlapane=w["zlapane"], po_akceptacji=w["po_akceptacji"], recenzent=w["recenzent"]))
    blame = collections.Counter(cache[k] if isinstance(cache[k], str) else "ok" for k in sprawdzone)
    blame["zamiatanie"] = len(zamiecione)
    return {"pr": wynik, "blame": blame, "od": od, "do": do}


def czas_uwagi_h(czasy: list, przerwa_min: int = PRZERWA_UWAGI_MIN) -> float:
    """Szacunek czasu uwagi właściciela: suma odstępów między kolejnymi wiadomościami nie dłuższych niż `przerwa_min`
    (wszystkie sesje razem, bo uwaga jest jedna). Praca poza Claude Code się nie liczy."""
    czasy = sorted(czasy)
    granica = dt.timedelta(minutes=przerwa_min)
    return sum(((b - a) for a, b in zip(czasy, czasy[1:]) if b - a <= granica), dt.timedelta()).total_seconds() / 3600


def podsumowanie(o: dict, rekordy: list = None, czasy_wlasciciela: list = None, konf: dict = None) -> dict:
    """Liczby kohorty: PR, zaakceptowane, %, przerobione, koszt okna kohorty i na zaakceptowany PR, wiadomości i godziny
    uwagi na zaakceptowany, złapane przez agentów / po akceptacji / produkcja, szczelność %."""
    lista = o["pr"]
    zaakc = sum(r["zaakceptowany"] for r in lista)
    koszt = sum(x["koszt"] for _, rek in rekordy for x in rek if o["od"] <= x["czas"] < o["do"]) if rekordy else None
    wiad = [c for c in czasy_wlasciciela if o["od"] <= c < o["do"]] if czasy_wlasciciela is not None else None
    przerwa = int((konf or {}).get("wynik_uwaga_przerwa_min") or PRZERWA_UWAGI_MIN)
    zlapane = sum(r["zlapane"] for r in lista)
    po_akc = sum(r["po_akceptacji"] for r in lista)
    prod = sum(len(r["produkcja"]) for r in lista)
    wszystkie_bledy = zlapane + po_akc + prod
    return {"pr": len(lista), "zaakceptowane": zaakc,
            "akceptacja": round(100 * zaakc / len(lista), 1) if lista else None,
            "przerobione": sum(1 for r in lista if r["przerobki"]),
            "koszt": koszt, "koszt_na_zaakceptowany": round(koszt / zaakc, 2) if koszt is not None and zaakc else None,
            "koszt_na_scalony": round(koszt / len(lista), 2) if koszt is not None and lista else None,
            "wiad": len(wiad) if wiad is not None else None,
            "wiad_na_zaakceptowany": round(len(wiad) / zaakc, 1) if wiad is not None and zaakc else None,
            "uwaga_h": round(czas_uwagi_h(wiad, przerwa), 1) if wiad is not None else None,
            "uwaga_h_na_zaakceptowany": round(czas_uwagi_h(wiad, przerwa) / zaakc, 2) if wiad is not None and zaakc else None,
            "zlapane": zlapane, "po_akceptacji": po_akc, "produkcja": prod,
            "szczelnosc": round(100 * zlapane / wszystkie_bledy, 1) if wszystkie_bledy else None}


def etykieta_impl(r) -> str:
    impl = r.get("pr_impl")
    if impl:
        return ef.konfiguracja(impl[1], impl[2])
    return t("rola_sesja") if r.get("pr_koszt") is not None else t("ef_wyn_bez_impl")


def etykieta_recenzenta(r) -> str:
    return ef.konfiguracja(*r["recenzent"]) if r.get("recenzent") else t("wy_bez_przegladu")


def wg(lista: list, klucz) -> dict:
    grupy = collections.defaultdict(list)
    for r in lista:
        grupy[klucz(r)].append(r)
    return grupy


def udzialy_akceptacji(lista: list) -> str:
    """„Opus · high:80;Sonnet · medium:60” → kolumna CSV z „/” zamiast „ · ”."""
    grupy = wg(lista, etykieta_impl)
    return ";".join(f"{k.replace(' · ', '/')}:{100 * sum(r['zaakceptowany'] for r in v) / len(v):.0f}"
                    for k, v in sorted(grupy.items(), key=lambda x: -len(x[1]))) or None


def udzialy_szczelnosci(lista: list) -> str:
    wynik = []
    for k, v in sorted(wg(lista, etykieta_recenzenta).items(), key=lambda x: -len(x[1])):
        z = sum(r["zlapane"] for r in v)
        razem = z + sum(r["po_akceptacji"] + len(r["produkcja"]) for r in v)
        if razem:
            wynik.append(f"{k.replace(' · ', '/')}:{100 * z / razem:.0f}")
    return ";".join(wynik) or None


def metryki(o, pods: dict) -> dict:
    """Kolumny `metryki.csv` od 0.9.0 (None bez danych z GitHuba)."""
    puste = {k: None for k in ("kohorta_od", "kohorta_do", "kohorta_pr", "akceptacja_proc", "akceptacja_proc_wg_impl",
                               "pr_przerobione_30d", "koszt_na_zaakceptowany_usd", "wiad_na_zaakceptowany",
                               "uwaga_h_na_zaakceptowany", "szczelnosc_proc", "bledy_zlapane_agenci",
                               "bledy_po_akceptacji", "bledy_produkcja", "szczelnosc_proc_wg_recenzenta")}
    if o is None:
        return puste
    return dict(puste, kohorta_od=f"{o['od']:%Y-%m-%d}", kohorta_do=f"{o['do'] - dt.timedelta(minutes=1):%Y-%m-%d}",
                kohorta_pr=pods["pr"], akceptacja_proc=pods["akceptacja"],
                akceptacja_proc_wg_impl=udzialy_akceptacji(o["pr"]), pr_przerobione_30d=pods["przerobione"],
                koszt_na_zaakceptowany_usd=pods["koszt_na_zaakceptowany"], wiad_na_zaakceptowany=pods["wiad_na_zaakceptowany"],
                uwaga_h_na_zaakceptowany=pods["uwaga_h_na_zaakceptowany"], szczelnosc_proc=pods["szczelnosc"],
                bledy_zlapane_agenci=pods["zlapane"], bledy_po_akceptacji=pods["po_akceptacji"],
                bledy_produkcja=pods["produkcja"], szczelnosc_proc_wg_recenzenta=udzialy_szczelnosci(o["pr"]))


# ---------------------------------------------------------------- raport

def gwiazdka(n: int) -> str:
    return "" if n >= ef.MIN_PR else "*"


def wiersze_wynikow(oceny: list) -> list:
    """Wiersze tabeli „Wyniki wobec poprzednich retro”: [(etykieta, komórki, kierunek)]. `oceny`: dla każdego okna
    (kolejność `efektywnosc.okna_retro`) wynik `podsumowanie` albo None (brak danych). Akceptacja i szczelność:
    więcej = lepiej; koszt na zaakceptowany: więcej = gorzej."""
    def kierunek(klucz, wiecej_lepiej):
        teraz = oceny[-1]
        if not teraz or teraz[klucz] is None or teraz["pr"] < ef.MIN_PR:
            return "—"
        wczesniej = [o[klucz] for o in oceny[:-1] if o and o[klucz] is not None and o["pr"] >= ef.MIN_PR]
        if not wczesniej:
            return "—"
        strz = tokeny.strzalka(statistics.median(wczesniej), teraz[klucz])
        if wiecej_lepiej:
            return {"↑": t("kier_lepiej_wzrost"), "↓": f"**{t('kier_gorzej_spadek')}**", "≈": "≈"}.get(strz, "—")
        return {"↑": f"**{t('kier_gorzej')}**", "↓": t("kier_lepiej"), "≈": "≈"}.get(strz, "—")

    def komorki(f):
        return ["—" if not o else f(o) for o in oceny]

    akc = komorki(lambda o: "—" if o["akceptacja"] is None else f"{o['akceptacja']:g}% ({o['zaakceptowane']}/{o['pr']}){gwiazdka(o['pr'])}")
    koszt = komorki(lambda o: "—" if o["koszt_na_zaakceptowany"] is None else f"${o['koszt_na_zaakceptowany']:.2f}{gwiazdka(o['pr'])}")
    szcz = komorki(lambda o: "—" if o["szczelnosc"] is None else
                   f"{o['szczelnosc']:g}% ({o['zlapane']}/{o['zlapane'] + o['po_akceptacji'] + o['produkcja']}){gwiazdka(o['pr'])}")
    return [(t("wy_wyn_akceptacja"), akc, kierunek("akceptacja", True)),
            (t("wy_wyn_koszt"), koszt, kierunek("koszt_na_zaakceptowany", False)),
            (t("wy_wyn_szczelnosc"), szcz, kierunek("szczelnosc", True))]


def raport(o, pods: dict, uwagi: list = (), progi=None, konf: dict = None) -> list:
    """Sekcja podsumowania „Miary wyniku” dla kohorty bieżącego okna."""
    l = ["", t("wy_tytul"), ""]
    if o is None:
        return l + [t("wy_brak")]
    dni = (o["do"] - o["od"]).days
    l += [t("wy_opis", od=f"{o['od']:%Y-%m-%d}", do=f"{o['do'] - dt.timedelta(minutes=1):%Y-%m-%d}", dni=dni,
            dni2=2 * dni, min_pr=ef.MIN_PR), ""]
    l += [f"- {u}" for u in uwagi]
    if not o["pr"]:
        return l + [t("wy_pusta")]
    usd = lambda v: "—" if v is None else f"${v:.2f}"  # noqa: E731
    pusty = lambda v: "—" if v is None else f"{v:g}"  # noqa: E731
    l += [t("wy_akceptacja", akc=pusty(pods["akceptacja"]), n=pods["zaakceptowane"], pr=pods["pr"],
            przerobione=pods["przerobione"], gw=gwiazdka(pods["pr"])),
          t("wy_koszt", koszt=usd(pods["koszt"]), na_zaakc=usd(pods["koszt_na_zaakceptowany"]),
            na_scal=usd(pods["koszt_na_scalony"]), wiad=pusty(pods["wiad"]), wiad_na=pusty(pods["wiad_na_zaakceptowany"]),
            h=pusty(pods["uwaga_h"]), h_na=pusty(pods["uwaga_h_na_zaakceptowany"])),
          t("wy_szczelnosc", szcz=pusty(pods["szczelnosc"]), zlapane=pods["zlapane"], po=pods["po_akceptacji"],
            prod=pods["produkcja"])]
    blame = o["blame"]
    if blame:
        l.append(t("wy_blame", ok=blame["ok"], klon=blame["brak_klonu"], commit=blame["brak_commita"],
                   zamiatanie=blame["zamiatanie"], prog=int((konf or {}).get("wynik_zamiatanie_pr") or ZAMIATANIE_PR)))
    # akceptacja wg implementatora i rozmiaru
    l += ["", t("wy_impl_kolumny"), "|---|---|---|---|---|"]
    kolejnosc = {"S": 0, "M": 1, "L": 2, "?": 3}
    grupy = wg(o["pr"], lambda r: (etykieta_impl(r), ef.rozmiar(r["linie"], progi)))
    for (impl, rozm), v in sorted(grupy.items(), key=lambda x: (kolejnosc[x[0][1]], -len(x[1]), x[0][0])):
        zaakc = sum(r["zaakceptowany"] for r in v)
        l.append(f"| {impl} | {rozm} | {len(v)}{gwiazdka(len(v))} | {100 * zaakc / len(v):.0f}% | "
                 f"{sum(1 for r in v if r['przerobki'])} |")
    # szczelność wg recenzenta
    l += ["", t("wy_rec_kolumny"), "|---|---|---|---|---|---|"]
    for rec, v in sorted(wg(o["pr"], etykieta_recenzenta).items(), key=lambda x: -len(x[1])):
        z, po, prod = (sum(r["zlapane"] for r in v), sum(r["po_akceptacji"] for r in v),
                       sum(len(r["produkcja"]) for r in v))
        szcz = f"{100 * z / (z + po + prod):.0f}%" if z + po + prod else "—"
        l.append(f"| {rec} | {len(v)}{gwiazdka(len(v))} | {z} | {po} | {prod} | {szcz} |")
    przerobione = [r for r in o["pr"] if r["przerobki"]]
    if przerobione:
        l += ["", t("wy_przerobione") + ", ".join(
            f"{r['repo']}#{r['pr']} ← " + ", ".join(f"#{n} ({t('wy_sposob_' + s)})" for n, s in r["przerobki"])
            for r in przerobione[:10]) + (", …" if len(przerobione) > 10 else "")]
    l += ["", t("wy_ograniczenia")]
    return l
