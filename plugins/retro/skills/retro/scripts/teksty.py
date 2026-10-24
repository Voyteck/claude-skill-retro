"""Komunikaty skryptów retro w językach pluginu (pole `jezyk` konfiguracji).

Obsługiwane: `pl`, `en`. Inny kod języka dostaje teksty angielskie (Claude pisze dokumenty retro w języku
użytkownika, a raporty skryptów to dla niego materiał źródłowy). Identyfikatory (nazwy plików, klucze konfiguracji,
kolumny CSV, klasy odpowiedzi) się nie zmieniają, żeby katalogi robocze i `metryki.csv` były zgodne między językami.

Nowy język: dopisz kod do JEZYKI i tłumaczenie do każdego wpisu TEKSTY (brakujący wpis spada na `en`).
"""
import re

JEZYKI = ("pl", "en")
ZAPASOWY = "en"
_jezyk = "pl"

# Rozpoznawanie niezależne od języka rozmowy -------------------------------------------------------------------

# Opcja rekomendowana w AskUserQuestion, w językach, w których najczęściej pisze się do Claude'a.
# „nie zalecane”, „not recommended”, „no recomendado”, „nicht empfohlen”, „non raccomandato” to nie rekomendacja.
WZOR_REKOMENDACJI = re.compile(
    r"(?<!nie )(?<!not )(?<!no )(?<!nicht )(?<!non )(?<!niet )"
    r"\b(rekomend\w*|zalec\w*|recommend\w*|recomend\w*|recommand\w*|raccomand\w*|empfohlen\w*|empfehl\w*"
    r"|aanbevolen|aanbevel\w*|doporuč\w*)",
    re.IGNORECASE,
)
# Pytanie o fakt znany tylko użytkownikowi („w jakiej sieci jesteś?”): nie ma opcji rekomendowanej z natury.
# Znacznik liczy się tylko na początku pytania; „[fakt]” w cytacie w środku treści nie robi z decyzji faktu.
ZNACZNIKI_FAKTU = ("[fakt]", "[fact]")


def pytanie_o_fakt(pytanie: str) -> bool:
    """Czy treść pytania zaczyna się (po ewentualnych odstępach) znacznikiem faktu."""
    return (pytanie or "").lstrip().lower().startswith(ZNACZNIKI_FAKTU)
# Status zakończonego retro w pliku `retro/RNN-RRRR-MM-DD.md` (szablony: pl „zakończone”, en „completed”).
WZOR_ZAKONCZONE = re.compile(r"\*\*Status:\*\*\s*(zakończone|zakonczone|completed|done|closed)\b", re.IGNORECASE)
# To samo dla `git log -G` (POSIX ERE, bez \b i flag).
WZOR_ZAKONCZONE_GIT = r"\*\*Status:\*\*[[:space:]]*([Zz]ako|[Cc]ompleted|[Dd]one|[Cc]losed)"

# Słowa „możliwej korekty” w wiadomościach właściciela, wg języka. Heurystyka: liczy się trend, nie wartość.
# Angielskie zawsze dochodzą, bo rozmowy techniczne je mieszają.
SLOWA_KOREKTY = {
    "pl": [r"nie ", "dlaczego", "czemu", "znowu", "ponownie", "przecież", "mówiłem", "mówiłam", "prosiłem",
           "prosiłam", "miałeś", "miałaś", "zapomnia", "źle", "błąd", "nie widzę", "gdzie jest", "czekaj",
           "zatrzymaj", "jeszcze raz"],
    "en": [r"why\b", r"again\b", r"wrong\b", r"don't\b", r"didn't\b", r"stop\b", r"wait\b", r"not what\b",
           r"i said\b", r"i asked\b", r"you forgot\b"],
}


def wzor_korekty(jezyk: str = None):
    slowa = list(SLOWA_KOREKTY.get(jezyk or _jezyk, []))
    slowa += [s for s in SLOWA_KOREKTY["en"] if s not in slowa]
    return re.compile(r"(^|\W)(" + "|".join(slowa) + ")", re.IGNORECASE)


# Teksty --------------------------------------------------------------------------------------------------------

TEKSTY = {
    # sygnaly.py: raport projektu
    "zamazane": {"pl": "[zamazane]", "en": "[redacted]"},
    "obraz": {"pl": "[obraz]", "en": "[image]"},
    "znak_korekty": {"pl": "[K?]", "en": "[C?]"},
    "proj_tytul": {"pl": "# {nazwa}: sygnały {od} … {do}", "en": "# {nazwa}: signals {od} … {do}"},
    "proj_sesje": {"pl": "## Sesje", "en": "## Sessions"},
    "proj_sesje_kolumny": {
        "pl": "| sesja | tytuł | aktywna | wiad. wł. | pytania (rek/inna/własna/odł.) | przerw. | blokady | błędy | kompakty | podagenci | koszt API |",
        "en": "| session | title | active | owner msgs | questions (rec/other/own/dism.) | interr. | blocks | errors | compacts | subagents | API cost |"},
    "proj_os": {"pl": "## Oś czasu", "en": "## Timeline"},
    "proj_legenda": {
        "pl": "Legenda: **[K?]** = heurystycznie możliwa korekta; klasy odpowiedzi: rekomendowana / inna / własna "
              "(tekst spoza opcji) / odłożone / bez wyboru / fakt (pytanie zaczynające się od „[fakt]” albo „[fact]”).",
        "en": "Legend: **[C?]** = possible correction (heuristic); answer classes: rekomendowana (recommended) / inna "
              "(other option) / wlasna (own text outside the options) / odlozone (dismissed) / bez_wyboru (no "
              "preference) / fakt (question starting with “[fact]” or “[fakt]”)."},
    "w_trakcie": {"pl": " (w trakcie pracy Claude'a)", "en": " (while Claude was working)"},
    "wlasciciel": {"pl": "Właściciel", "en": "Owner"},
    "wczesniej_claude": {"pl": "  - ↳ wcześniej Claude: _{tekst}_", "en": "  - ↳ Claude before: _{tekst}_"},
    "zd_pytanie": {"pl": "**Pytanie:**", "en": "**Question:**"},
    "zd_blokada": {"pl": "**Blokada klasyfikatora**", "en": "**Classifier block**"},
    "zd_odmowa": {"pl": "**Odmowa właściciela**", "en": "**Owner denial**"},
    "zd_przerwanie": {"pl": "**Przerwanie przez właściciela.** Wcześniej Claude: _{tekst}_",
                      "en": "**Interrupted by the owner.** Claude before: _{tekst}_"},
    "zd_polecenie": {"pl": "Polecenie `{polecenie}`", "en": "Command `{polecenie}`"},
    "zd_kompakt": {"pl": "Kompakt kontekstu", "en": "Context compaction"},
    "proj_bledy": {"pl": "## Najczęstsze błędy narzędzi", "en": "## Most frequent tool errors"},
    "proj_podagenci": {"pl": "## Podagenci", "en": "## Subagents"},
    "proj_podagenci_zadane": {"pl": "Wywołania (typ, model zadany w wywołaniu):",
                              "en": "Calls (type, model requested in the call):"},
    "proj_podagenci_faktyczne": {"pl": "Faktycznie uruchomieni (typ, model z ich transkrypcji):",
                                 "en": "Actually run (type, model from their transcripts):"},
    "dziedziczony": {"pl": "dziedziczony", "en": "inherited"},
    "proj_pr": {"pl": "## PR-y wspomniane w sesjach", "en": "## PRs mentioned in sessions"},

    # sygnaly.py: pory dnia
    "pora_noc_przed": {"pl": "noc (przed {od})", "en": "night (before {od})"},
    "pora_dzien": {"pl": "dzień ({od}–{do})", "en": "day ({od}–{do})"},
    "pora_wieczor": {"pl": "wieczór ({do}–{wieczor})", "en": "evening ({do}–{wieczor})"},
    "pora_noc_po": {"pl": "noc (po {wieczor})", "en": "night (after {wieczor})"},

    # sygnaly.py: trend
    "trend_tytul": {"pl": "## Trend tokenów (tydzień po tygodniu)", "en": "## Token trend (week by week)"},
    "trend_pominiety": {"pl": "Trend {uwaga}.", "en": "Trend {uwaga}."},
    "trend_opis": {
        "pl": "Plik `{plik}` w katalogu roboczym (commitowany; archiwum liczb: `{archiwum}`). Ostatnie {ostatnie} "
              "zakończone tygodnie z aktywnością wobec mediany {wczesniej} wcześniejszych; zmiana o więcej niż {prog} "
              "to strzałka. Dla każdego wskaźnika więcej = gorzej; **↑** oznacza pogorszenie.",
        "en": "File `{plik}` in the working directory (committed; number archive: `{archiwum}`). The last {ostatnie} "
              "completed weeks with activity against the median of the {wczesniej} before them; a change of more than "
              "{prog} gets an arrow. For every indicator more = worse; **↑** means getting worse."},
    "trend_zdalne": {"pl": "Źródła zdalne (`zrodla_zdalne`):", "en": "Remote sources (`zrodla_zdalne`):"},
    "trend_kilka_wierszy": {"pl": "Źródło `{zrodlo}`: kilka wierszy na tydzień (pomiary okienne), bez tabeli trendu.",
                            "en": "Source `{zrodlo}`: several rows per week (window measurements), no trend table."},
    "trend_zrodlo": {"pl": "Źródło `{zrodlo}`:", "en": "Source `{zrodlo}`:"},
    "trend_kolumny": {
        "pl": "| wskaźnik | mediana wcześniej (tyg.) | ostatnie tygodnie | mediana ostatnich | kierunek |",
        "en": "| indicator | earlier median (weeks) | recent weeks | recent median | direction |"},
    "trend_kolumna_biezacy": {"pl": " tydzień {tydzien} (niezakończony)", "en": " week {tydzien} (not finished)"},
    "trend_biezacy_opis": {
        "pl": "Ostatnia kolumna: bieżący tydzień, jeszcze niezakończony i poza porównaniem. Strzałka przy nim (wobec "
              "mediany ostatnich tygodni) pokazuje świeżą poprawkę albo pogorszenie od razu; to kilka dni danych, więc "
              "wskazówka, nie wynik. Sumy tygodnia (koszt tygodnia, koszt wybudzeń) jeszcze rosną: przy nich tylko ↑.",
        "en": "Last column: the current week, not finished yet and outside the comparison. Its arrow (against the "
              "recent median) shows a fresh improvement or deterioration at once; it is a few days of data, so a hint, "
              "not a result. Weekly sums (weekly cost, wake-up cost) are still growing: they only get ↑."},
    "trend_gorsze": {"pl": "**Pogarsza się ({zrodlo}):** ", "en": "**Getting worse ({zrodlo}):** "},
    "trend_bez": {"pl": "pominięty (`--bez-trendu` albo brak katalogu roboczego)",
                  "en": "skipped (`--bez-trendu` or no working directory)"},
    "trend_projekt": {"pl": "pominięty, bo `--projekt` zawęża zakres (trend dotyczy całego zakresu retro)",
                      "en": "skipped because `--projekt` narrows the scope (the trend covers the whole retro scope)"},
    "zdalne_pominiete": {"pl": "`{nazwa}`: pominięte (`--bez-zdalnych`)", "en": "`{nazwa}`: skipped (`--bez-zdalnych`)"},
    "zdalne_brak": {"pl": "`{nazwa}`: **brak odczytu** ({opis}); trend tego źródła bez nowych danych",
                    "en": "`{nazwa}`: **not read** ({opis}); this source's trend has no new data"},
    "zdalne_ok": {"pl": "`{nazwa}`: {opis}, {odczyt} wywołań w odczycie, {archiwum} w archiwum `{plik}`",
                  "en": "`{nazwa}`: {opis}, {odczyt} calls read, {archiwum} in archive `{plik}`"},

    # tokeny.py: wskaźniki i kierunki trendu, uwagi w kolumnie `pokrycie`
    "wsk_koszt_na_wiad": {"pl": "koszt na wiadomość (USD)", "en": "cost per message (USD)"},
    "wsk_wywolania_na_wiad": {"pl": "wywołania API na wiadomość", "en": "API calls per message"},
    "wsk_kontekst_mediana": {"pl": "mediana kontekstu sesji głównej", "en": "median main-session context"},
    "wsk_proc_wywolan_ponad_200k": {"pl": "% wywołań sesji głównej > 200k", "en": "% main-session calls > 200k"},
    "wsk_wybudzenia_koszt_usd": {"pl": "koszt wybudzeń (USD)", "en": "wake-up cost (USD)"},
    "wsk_proc_kosztu_podagentow_opus": {"pl": "% kosztu podagentów na Opusie", "en": "% of subagent cost on Opus"},
    "wsk_kontekst_startowy_mediana": {"pl": "kontekst startowy sesji", "en": "session starting context"},
    "wsk_koszt_api_usd": {"pl": "koszt tygodnia (USD)", "en": "weekly cost (USD)"},
    "kier_malo": {"pl": "za mało danych", "en": "not enough data"},
    "kier_gorzej": {"pl": "↑ pogorszenie", "en": "↑ worse"},
    "kier_lepiej": {"pl": "↓ poprawa", "en": "↓ better"},
    "pokr_niezakonczony": {"pl": "okres niezakończony", "en": "period not finished"},
    "pokr_brak": {"pl": "brak aktywności", "en": "no activity"},
    "pokr_poprzedni": {"pl": "wiersz z poprzedniego przebiegu (teraz {n} wywołań, reszta usunięta przez retencję)",
                       "en": "row from a previous run (now {n} calls, the rest removed by retention)"},
    "zr_polecenie_blad": {"pl": "polecenie nie zadziałało: {blad}", "en": "the command failed: {blad}"},
    "zr_polecenie_kod": {"pl": "polecenie zwróciło {kod}: {blad}", "en": "the command returned {kod}: {blad}"},
    "zr_polecenie_ok": {"pl": "odczyt poleceniem", "en": "read by command"},
    "zr_nie_json": {"pl": "polecenie nie zwróciło JSON-a: {wyjscie}", "en": "the command did not return JSON: {wyjscie}"},
    "zr_plik_blad": {"pl": "nie da się odczytać pliku `{plik}`: {blad}", "en": "cannot read file `{plik}`: {blad}"},
    "zr_plik_ok": {"pl": "plik `{plik}` z {kiedy}", "en": "file `{plik}` from {kiedy}"},
    "zr_brak_pol": {"pl": "brak pola `polecenie` ani `plik`", "en": "neither `polecenie` nor `plik` is set"},

    # sygnaly.py: tokeny i koszt
    "tok_tytul": {"pl": "## Tokeny i koszt (ceny API, miara względna)",
                  "en": "## Tokens and cost (API prices, relative measure)"},
    "tok_opis": {
        "pl": "Ceny z `references/cennik.json` (stan na {stan}; nadpisuje je pole `cennik` w konfiguracji). To miara "
              "względna, nie rachunek: konto na subskrypcji płaci limitem. Dolne oszacowanie, bo wywołania spoza "
              "transkrypcji (klasyfikator trybu auto, tytuły sesji) nie są liczone. Wywołanie = unikalny `message.id`, "
              "razem z transkrypcjami podagentów. Szczegóły i ograniczenia: `references/sygnaly.md`.",
        "en": "Prices from `references/cennik.json` (as of {stan}; the `cennik` config field overrides them). This is a "
              "relative measure, not a bill: a subscription account pays with its limit. A lower bound, because calls "
              "outside the transcripts (auto mode classifier, session titles) are not counted. A call = a unique "
              "`message.id`, subagent transcripts included. Details and limits: `references/sygnaly.md`."},
    "tok_kolumny": {"pl": "| | wartość |", "en": "| | value |"},
    "tok_wywolania": {"pl": "wywołania API", "en": "API calls"},
    "tok_koszt": {"pl": "koszt", "en": "cost"},
    "tok_cache": {"pl": "trafienia cache (odczyt / cały kontekst)", "en": "cache hits (read / whole context)"},
    "tok_wyjscie": {"pl": "tokeny wyjścia", "en": "output tokens"},
    "tok_kontekst": {"pl": "mediana kontekstu sesji głównej", "en": "median main-session context"},
    "tok_ponad": {"pl": "wywołania sesji głównej > {prog}k", "en": "main-session calls > {prog}k"},
    "tok_startowy": {"pl": "kontekst startowy, mediana ({n} sesji zaczętych w oknie)",
                     "en": "starting context, median ({n} sessions started in the window)"},
    "tok_podagenci": {"pl": "udział podagentów w koszcie", "en": "subagent share of cost"},
    "tok_opus": {"pl": "udział Opusa w koszcie podagentów", "en": "Opus share of subagent cost"},
    "tok_wybudzenia": {"pl": "wybudzenia (zapis cache > {tokeny}k po przerwie > {h} h)",
                       "en": "wake-ups (cache write > {tokeny}k after a break > {h} h)"},
    "tok_modele": {"pl": "Koszt wg modelu: ", "en": "Cost by model: "},
    "tok_drogie": {"pl": "Najdroższe sesje:", "en": "Most expensive sessions:"},
    "tok_lista_wybudzen": {"pl": "Wybudzenia (koszt samego zapisu cache):", "en": "Wake-ups (cost of the cache write only):"},
    "tok_wybudzenie": {"pl": "po {h:.1f} h: zapis {zapis}, ${koszt:.2f}; obudziło: {przyczyna}",
                       "en": "after {h:.1f} h: write {zapis}, ${koszt:.2f}; woken by: {przyczyna}"},
    "tok_przyczyny": {
        "pl": "Kto obudził sesję (pierwsze wejście po przerwie): {lista}. Hook na wiadomość właściciela "
              "(`UserPromptSubmit`) widzi tylko pierwszą przyczynę; zadania w tle i inne sesje budzą sesję bez niego.",
        "en": "What woke the session (first input after the break): {lista}. A hook on the owner's message "
              "(`UserPromptSubmit`) sees only the first cause; background tasks and other sessions wake it without one."},
    "przyczyna_wlasciciel": {"pl": "wiadomość właściciela", "en": "owner's message"},
    "przyczyna_tlo": {"pl": "zadanie lub podagent w tle", "en": "background task or subagent"},
    "przyczyna_sesja": {"pl": "inna sesja", "en": "another session"},
    "przyczyna_inne": {"pl": "inne (np. wynik narzędzia po długim czekaniu)",
                       "en": "other (e.g. a tool result after a long wait)"},
    "tok_nieznane": {
        "pl": "**Uwaga:** modeli bez ceny w cenniku nie wliczono do kosztu: {lista}. Dopisz je do pola `cennik` "
              "w konfiguracji albo do `references/cennik.json` w repo pluginu.",
        "en": "**Note:** models without a price in the price list are not included in the cost: {lista}. Add them to "
              "the `cennik` config field or to `references/cennik.json` in the plugin repo."},
    "tok_wywolan": {"pl": "{n} wywołań", "en": "{n} calls"},

    # efektywnosc.py: tokeny i efektywność pisania
    "rola_sesja": {"pl": "sesja główna", "en": "main session"},
    "rola_implementacja": {"pl": "implementacja", "en": "implementation"},
    "rola_przeglad": {"pl": "przegląd", "en": "review"},
    "rola_ci": {"pl": "CI", "en": "CI"},
    "rola_architekt": {"pl": "architekt", "en": "architect"},
    "rola_inne": {"pl": "inne podagenty", "en": "other subagents"},
    "ef_bez_stopki": {"pl": "bez stopki", "en": "no trailer"},
    "ef_tytul": {"pl": "## Tokeny i efektywność pisania", "en": "## Tokens and writing efficiency"},
    "ef_opis": {
        "pl": "Porównanie z poprzednimi retro (`metryki.csv`), koszt wg roli agenta i modelu, rundy poprawek "
              "w scalonych PR i powroty od przeglądu i CI. Dane do sekcji „2a” dokumentu retro; ograniczenia "
              "pomiaru: `references/sygnaly.md`.",
        "en": "Comparison with previous retros (`metryki.csv`), cost by agent role and model, fix rounds in merged PRs "
              "and returns from review and CI. Data for section \"2a\" of the retro document; measurement limits: "
              "`references/sygnaly.md`."},
    "ef_porownanie": {"pl": "### Wobec poprzednich retro", "en": "### Against previous retros"},
    "ef_porownanie_brak": {"pl": "Brak wcześniejszych wierszy w `metryki.csv`.",
                           "en": "No earlier rows in `metryki.csv`."},
    "ef_metryka": {"pl": "metryka", "en": "metric"},
    "ef_teraz": {"pl": "teraz", "en": "now"},
    "ef_kierunek": {"pl": "kierunek (wobec mediany poprzednich; więcej = gorzej)",
                    "en": "direction (against the previous median; more = worse)"},
    "ef_koszt_rol": {"pl": "### Koszt wg roli i modelu: `{zrodlo}` (USD w cenach bieżących modeli rodziny; % tygodnia)",
                     "en": "### Cost by role and model: `{zrodlo}` (USD at current model prices of the family; % of week)"},
    "ef_niezak": {"pl": " (niezak.)", "en": " (unfin.)"},
    "ef_rola_model": {"pl": "rola · model", "en": "role · model"},
    "ef_razem": {"pl": "razem", "en": "total"},
    "ef_rundy": {"pl": "### Rundy poprawek w scalonych PR (GitHub)", "en": "### Fix rounds in merged PRs (GitHub)"},
    "ef_rundy_opis": {
        "pl": "Runda = kolejna paczka commitów w PR po przerwie > {przerwa} min (data autorstwa, odporna na rebase). "
              "Pierwsza paczka to praca, kolejne to powroty: po przeglądzie, czerwonym CI, uwagach właściciela, ale "
              "też po rebase. Model autora = najczęstsza stopka `Co-Authored-By: Claude <Model>` w pierwszej paczce.",
        "en": "Round = another batch of commits in a PR after a break > {przerwa} min (author date, robust to rebase). "
              "The first batch is the work, the next ones are returns: after review, red CI, the owner's remarks, but "
              "also after a rebase. Author model = the most frequent `Co-Authored-By: Claude <Model>` trailer in the "
              "first batch."},
    "ef_pr": {"pl": "PR", "en": "PRs"},
    "ef_z_poprawka": {"pl": "z poprawką", "en": "with a fix"},
    "ef_rund_na_pr": {"pl": "rund na PR", "en": "rounds per PR"},
    "ef_commitow_na_pr": {"pl": "commitów na PR", "en": "commits per PR"},
    "ef_mediana_h": {"pl": "mediana h do scalenia", "en": "median h to merge"},
    "ef_tydzien_scalenia": {"pl": "tydzień scalenia", "en": "merge week"},
    "ef_okno": {"pl": "okno retro", "en": "retro window"},
    "ef_model_autora": {"pl": "model autora", "en": "author model"},
    "ef_tydzien": {"pl": "tydzień", "en": "week"},
    "ef_komorka": {"pl": "{pr} PR, {proc}% z popr.", "en": "{pr} PRs, {proc}% fixed"},
    "ef_kto_poprawia": {"pl": "Kto pisał commity poprawek (model autora PR → model commitu poprawki): ",
                        "en": "Who wrote the fix commits (PR author model → fix commit model): "},
    "ef_powroty": {"pl": "### Powroty od przeglądu i CI w transkrypcjach: `{zrodlo}` (okno retro)",
                   "en": "### Returns from review and CI in transcripts: `{zrodlo}` (retro window)"},
    "ef_powroty_brak": {"pl": "Brak uruchomień podagentów z rolą implementacji, przeglądu albo CI.",
                        "en": "No subagent runs with an implementation, review or CI role."},
    "ef_powroty_opis": {
        "pl": "Powrót = implementator uruchomiony albo kontynuowany na tym samym PR po negatywnym werdykcie przeglądu "
              "albo czerwonym CI. Przegląd i CI przypisane do ostatniego implementatora tego PR w sesji; bez niego "
              "do sesji głównej (jej własne poprawki nie są liczone jako powroty).",
        "en": "Return = the implementer started or continued on the same PR after a negative review verdict or red "
              "CI. Review and CI are assigned to the last implementer of that PR in the session; without one to the "
              "main session (its own fixes are not counted as returns)."},
    "ef_powroty_kolumny": {"pl": "| implementator · model | uruchomienia | przeglądy (negatywne) | CI (porażki) | powroty |",
                           "en": "| implementer · model | runs | reviews (negative) | CI (failures) | returns |"},
    "ef_powroty_przyczyny": {"pl": "Powroty wg przyczyny: przegląd {przeglad}, CI {ci}.",
                             "en": "Returns by cause: review {przeglad}, CI {ci}."},
    "ef_ograniczenia": {
        "pl": "Role agentów: pole `role_agentow` konfiguracji. Runda to nie zawsze powrót od testera (rebase, konflikty "
              "partii integracyjnych); stopka bywa pominięta; werdykt i wynik CI to heurystyka na raporcie podagenta. "
              "Mało PR jednego modelu (< 5) to wskazówka, nie wynik.",
        "en": "Agent roles: the `role_agentow` config field. A round is not always a return from the tester (rebase, "
              "integration batch conflicts); the trailer is sometimes missing; verdict and CI result are a heuristic on "
              "the subagent's report. Few PRs of one model (< 5) are a hint, not a result."},
    "ef_gh_pominiety": {"pl": "Rundy poprawek pominięte (brak gh albo `--bez-gh`).",
                        "en": "Fix rounds skipped (no gh or `--bez-gh`)."},
    "ef_gh_blad": {"pl": "Rundy poprawek `{repo}`: błąd gh ({blad}).", "en": "Fix rounds `{repo}`: gh error ({blad})."},
    "ef_koszt_bez_trendu": {"pl": "Koszt wg roli pominięty: wymaga archiwum trendu (bez `--bez-trendu` i `--projekt`).",
                            "en": "Cost by role skipped: it needs the trend archive (without `--bez-trendu` and `--projekt`)."},
    "ef_zdarzenia_brak": {"pl": "Zdarzenia agentów `{nazwa}`: **brak odczytu** ({opis}).",
                          "en": "Agent events `{nazwa}`: **not read** ({opis})."},
    "ef_zdarzenia_ok": {"pl": "Zdarzenia agentów `{nazwa}`: {opis}, {n} zdarzeń.",
                        "en": "Agent events `{nazwa}`: {opis}, {n} events."},
    "ef_konf_tytul": {"pl": "### Koszt i jakość na PR wg konfiguracji implementatora (model · poziom rozumowania)",
                      "en": "### Cost and quality per PR by implementer configuration (model · reasoning effort)"},
    "ef_konf_opis": {
        "pl": "Scalone PR z kilku tygodni, do których transkrypcje przypisują pracę podagentów (numer PR w zadaniu albo "
              "kontynuacji). Konfiguracja = model i poziom rozumowania pierwszego implementatora PR („sesja główna”, gdy "
              "pracowali tylko przegląd albo CI). Rozmiar: S ≤ {s} linii, M ≤ {m}, L > {m}. **Koszt na PR** to średni koszt "
              "agentów (implementacja, przegląd, CI, także w rundach poprawek), czyli oczekiwany koszt zaakceptowanego PR; "
              "porównuj go tylko w tym samym rozmiarze. Ceny bieżących modeli rodziny, bez kosztu sesji głównej; "
              "dlatego wiersz „sesja główna” (implementacja w sesji) ma tylko jakość i koszt kontroli. "
              "* = mniej niż {min_pr} PR: wskazówka, nie wynik.",
        "en": "Merged PRs from several weeks to which transcripts attribute subagent work (PR number in the task or a "
              "continuation). Configuration = model and reasoning effort of the PR's first implementer (\"main session\" "
              "when only review or CI worked on it). Size: S ≤ {s} lines, M ≤ {m}, L > {m}. **Cost per PR** is the mean "
              "agent cost (implementation, review, CI, fix rounds included), i.e. the expected cost of an accepted PR; "
              "compare it only within one size. Current model prices of the family, main-session cost excluded; that "
              "is why the \"main session\" row (implementation in the session) has only quality and control cost. "
              "* = fewer than {min_pr} PRs: a hint, not a result."},
    "ef_konf_brak": {"pl": "Brak scalonych PR z przypisanym kosztem agentów.",
                     "en": "No merged PRs with attributed agent cost."},
    "ef_konf_kolumny": {
        "pl": "| implementator | rozmiar | PR | z poprawką | rund na PR | implementacja / PR | przegląd i CI / PR | koszt na PR | na 100 linii |",
        "en": "| implementer | size | PRs | with a fix | rounds per PR | implementation / PR | review and CI / PR | cost per PR | per 100 lines |"},
    "ef_konf_bez_kosztu": {
        "pl": "PR bez przypisanej pracy agentów: {bez} z {wszystkie} (pisane w sesji głównej albo w transkrypcjach, "
              "których skrypt nie widzi; ich jakość jest w tabeli wg modelu autora).",
        "en": "PRs without attributed agent work: {bez} of {wszystkie} (written in the main session or in transcripts "
              "the script does not see; their quality is in the author model table)."},
    "ef_agenci_tytul": {"pl": "### Obecna konfiguracja agentów (`.claude/agents`)",
                        "en": "### Current agent configuration (`.claude/agents`)"},
    "ef_agenci_kolumny": {"pl": "| agent | rola | model | poziom | źródło |", "en": "| agent | role | model | effort | source |"},

    # sygnaly.py: podsumowanie
    "brak_katalogu": {
        "pl": "Nie znaleziono katalogu roboczego retro. Załóż go skryptem zaloz.py --tryb konto|projekt (patrz SKILL.md).",
        "en": "No retro working directory found. Create one with zaloz.py --tryb konto|projekt (see SKILL.md)."},
    "zla_data": {"pl": "Zła data w --od/--do: {blad}", "en": "Bad date in --od/--do: {blad}"},
    "pocz_podany": {"pl": "podany w `--od`", "en": "given in `--od`"},
    "pocz_polnoc": {"pl": "od północy", "en": "from midnight"},
    "pocz_commit": {"pl": "od commita, który zakończył {retro}", "en": "from the commit that completed {retro}"},
    "zakres_projekt": {"pl": "projekt `{repo}`", "en": "project `{repo}`"},
    "zakres_konto": {"pl": "całe konto (wszystkie projekty z transkrypcji)",
                     "en": "whole account (all projects in the transcripts)"},
    "zakres_zawezone": {"pl": ", zawężone do: {lista}", "en": ", narrowed to: {lista}"},
    "pods_tytul": {"pl": "# Sygnały do retro: {od} … {do}", "en": "# Retro signals: {od} … {do}"},
    "pods_wstep": {
        "pl": "Wygenerowano {kiedy} skryptem `scripts/sygnaly.py` skillu retro. Zakres: {zakres}. Liczby z heurystyk "
              "(np. „możliwa korekta”) są wskazówką, nie dowodem: dowodem jest wpis w osi czasu projektu.",
        "en": "Generated {kiedy} by `scripts/sygnaly.py` of the retro skill. Scope: {zakres}. Heuristic numbers (e.g. "
              "“possible correction”) are hints, not evidence: the evidence is the entry in the project timeline."},
    "pods_okno": {"pl": "Okno: {od} … {do} 23:59 ({poczatek}).", "en": "Window: {od} … {do} 23:59 ({poczatek})."},
    "pods_uwagi_danych": {
        "pl": "Wiadomości właściciela wysłane w trakcie pracy Claude'a: {w_trakcie} (wliczone w `wiad_wlasciciela`). "
              "Pominięte sesje uruchomione w scratchpadzie (np. testy `claude -p`): {scratchpad}. Ciągi wyglądające na "
              "sekrety zamazane w osiach czasu: {zamazane} (heurystyka; patrz `references/sygnaly.md`).",
        "en": "Owner messages sent while Claude was working: {w_trakcie} (included in `wiad_wlasciciela`). Skipped "
              "sessions started in a scratchpad (e.g. `claude -p` tests): {scratchpad}. Secret-like strings redacted "
              "in the timelines: {zamazane} (heuristic; see `references/sygnaly.md`)."},
    "pods_retencja": {
        "pl": "**Uwaga:** okno zaczyna się {dni} dni temu, a Claude Code usuwa transkrypcje starsze niż {retencja} dni "
              "(`cleanupPeriodDays`). Sesje sprzed {data} mogły już zniknąć z dysku, więc liczby dla początku okna są "
              "zaniżone.",
        "en": "**Note:** the window starts {dni} days ago, and Claude Code deletes transcripts older than {retencja} "
              "days (`cleanupPeriodDays`). Sessions before {data} may already be gone from disk, so the numbers for "
              "the start of the window are too low."},
    "pods_metryki": {"pl": "## Metryki", "en": "## Metrics"},
    "pods_metryki_kolumny": {"pl": "| metryka | wartość |", "en": "| metric | value |"},
    "pods_projekty": {"pl": "## Projekty", "en": "## Projects"},
    "pods_projekty_kolumny": {
        "pl": "| projekt | sesje | wiad. wł. | [K?] | pytania | rek. | inna | własna | odłożone | fakt | przerw. | blokady | błędy | kompakty | podagenci | koszt API |",
        "en": "| project | sessions | owner msgs | [C?] | questions | rec. | other | own | dismissed | fact | interr. | blocks | errors | compacts | subagents | API cost |"},
    "pods_pory": {"pl": "## Pora wiadomości właściciela", "en": "## Time of owner messages"},
    "pods_repo": {"pl": "## Repozytoria", "en": "## Repositories"},
    "pods_repo_kolumny": {
        "pl": "| repo | ścieżka | commity | bez lok. sesji | fix | revert | zmiany reguł | PR otw. | bez lok. sesji | PR scal. | mediana h do scalenia | mediana commitów/PR | CI porażki/wszystkie | za zdalną | gh |",
        "en": "| repo | path | commits | no local session | fix | revert | rule changes | PRs opened | no local session | PRs merged | median h to merge | median commits/PR | CI failed/all | behind remote | gh |"},
    "gh_ok": {"pl": "ok", "en": "ok"},
    "gh_pominiety": {"pl": "pominięty (brak gh albo --bez-gh)", "en": "skipped (no gh or --bez-gh)"},
    "gh_brak_zdalnego": {"pl": "brak zdalnego", "en": "no remote"},
    "gh_blad": {"pl": "błąd: {blad}", "en": "error: {blad}"},
    "gh_40": {"pl": "ok (commity/PR z 40 najnowszych)", "en": "ok (commits/PR from the 40 newest)"},
    "pods_poza": {
        "pl": "**Uwaga:** część pracy w repozytoriach nie ma lokalnych transkrypcji (brak zapisu sesji tego repo "
              "w odstępie ±{margines} min): {lista}. To zwykle sandbox, sesje w chmurze, inna maszyna albo scalenia na "
              "GitHubie. Osie czasu, pytania i koszt tej pracy nie widzą, więc nie zestawiaj ich z commitami tych repo "
              "(np. koszt na PR). Transkrypcje skopiowane z innej maszyny dołącza pole `transkrypcje_dodatkowe` "
              "w konfiguracji.",
        "en": "**Note:** some work in these repositories has no local transcripts (no session record for the repo "
              "within ±{margines} min): {lista}. Usually a sandbox, cloud sessions, another machine or merges on "
              "GitHub. Timelines, questions and cost do not see this work, so do not set them against these repos' "
              "commits (e.g. cost per PR). Transcripts copied from another machine are added with the "
              "`transkrypcje_dodatkowe` config field."},
    "pods_poza_repo": {"pl": "{n}: {bez} z {wszystkie} commitów", "en": "{n}: {bez} of {wszystkie} commits"},
    "pods_poza_pr": {"pl": ", {bez} z {wszystkie} otwartych PR", "en": ", {bez} of {wszystkie} opened PRs"},
    "pods_reguly": {"pl": "## Pliki reguł (linie)", "en": "## Rule files (lines)"},
    "pods_reguly_osobno": {
        "pl": "Liczone osobno (`katalogi_regul_osobno`), poza `claude_md_linie`: {linie} linii w {pliki} plikach.",
        "en": "Counted separately (`katalogi_regul_osobno`), outside `claude_md_linie`: {linie} lines in {pliki} files."},
    "pods_kopie": {
        "pl": "**Uwaga:** katalogi z wieloma zagnieżdżonymi `CLAUDE.md`, liczone w `claude_md_linie`: {lista}. Jeśli to "
              "kopie dla przyszłych repozytoriów (a nie reguły, które ładują sesje w tym repo), dopisz katalog do "
              "`katalogi_regul_osobno`.",
        "en": "**Note:** directories with many nested `CLAUDE.md` files, counted in `claude_md_linie`: {lista}. If "
              "these are copies for future repositories (not rules that sessions in this repo load), add the "
              "directory to `katalogi_regul_osobno`."},
    "pods_kopie_poz": {"pl": "{n} `{k}`: {p} plików, {li} linii", "en": "{n} `{k}`: {p} files, {li} lines"},
    "pods_w_tyle": {
        "pl": "**Uwaga:** checkout jest za zdalną gałęzią (wg ostatniego `git fetch`), więc liczby linii reguł i ich "
              "treść na dysku mogą być nieaktualne: {lista}. Czytaj reguły z `git show @{{u}}:CLAUDE.md`.",
        "en": "**Note:** the checkout is behind its remote branch (as of the last `git fetch`), so rule line counts "
              "and their content on disk may be stale: {lista}. Read the rules with `git show @{{u}}:CLAUDE.md`."},
    "pods_w_tyle_poz": {"pl": "{n} o {k} commitów", "en": "{n} by {k} commits"},
    "pods_reguly_opis": {
        "pl": "Liczone są pliki `CLAUDE.md` (śledzone na dowolnej głębokości), `CLAUDE.local.md` i "
              "`pliki_regul_dodatkowe` z konfiguracji. Inne pliki, do których reguły odsyłają jako wiążących, dopisz "
              "do `pliki_regul_dodatkowe`; katalogi z kopiami reguł dla innych repozytoriów do `katalogi_regul_osobno`.",
        "en": "Counted: `CLAUDE.md` files (tracked at any depth), `CLAUDE.local.md` and `pliki_regul_dodatkowe` from "
              "the config. Add other files the rules point to as binding to `pliki_regul_dodatkowe`; directories with "
              "rule copies for other repositories to `katalogi_regul_osobno`."},
    "pods_pamiec": {"pl": "## Pamięć: {pliki} plików, zmienione w oknie: {zmiany}",
                    "en": "## Memory: {pliki} files, changed in the window: {zmiany}"},
    "pods_pamiec_bez_sesji": {
        "pl": "Projekty z pamięcią, ale bez lokalnej sesji w oknie (praca gdzie indziej albo projekt uśpiony; ich repo "
              "i pliki reguł nie są tu liczone, dodaj je w `repozytoria_dodatkowe`):",
        "en": "Projects with memory but no local session in the window (work elsewhere or a dormant project; their "
              "repos and rule files are not counted here, add them in `repozytoria_dodatkowe`):"},
    "pods_pamiec_poz": {"pl": "- …{folder}: {n} plików pamięci", "en": "- …{folder}: {n} memory files"},
    "pods_ok": {"pl": "OK: {sesje} sesji, {projekty} projektów, {repo} repo, zamazane sekrety: {zamazane} -> {wyjscie}",
                "en": "OK: {sesje} sessions, {projekty} projects, {repo} repos, redacted secrets: {zamazane} -> {wyjscie}"},

    # przypomnienie.py
    "przyp_ostatnie": {"pl": "ostatnie retro R{numer:02d} zakończone {data}, {dni} dni roboczych temu",
                       "en": "the last retro R{numer:02d} was completed on {data}, {dni} working days ago"},
    "przyp_zadnego": {"pl": "nie ma jeszcze żadnego zakończonego retro", "en": "no retro has been completed yet"},
    "przyp_w_projekcie": {"pl": "w tym projekcie", "en": "in this project"},
    "przyp_w_katalogu": {"pl": "w sesji w {katalog}", "en": "in a session in {katalog}"},
    "przyp_komunikat": {"pl": "Retro zaległe: {opis}. Uruchom {polecenie} ({gdzie}).",
                        "en": "Retro overdue: {opis}. Run {polecenie} ({gdzie})."},
    "przyp_kontekst": {
        "pl": "Przypomnienie o retrospektywie (skill retro): {opis} (próg {prog} dni roboczych). Nie przerywaj zadania "
              "użytkownika. Na końcu pierwszej odpowiedzi w tej sesji zapytaj go (AskUserQuestion, jeśli jest "
              "dostępne), czy robimy retro: „Dziś, w osobnej sesji (rekomendowane)” ({gdzie}, polecenie {polecenie}, "
              "ok. 20–40 min), „Jutro”, „Pomiń tym razem”. Samego retro nie uruchamiaj bez jego zgody.",
        "en": "Retrospective reminder (retro skill): {opis} (threshold {prog} working days). Do not interrupt the "
              "user's task. At the end of your first reply in this session ask them (AskUserQuestion if available), "
              "in their language, whether to do the retro: “Today, in a separate session (Recommended)” ({gdzie}, "
              "command {polecenie}, about 20–40 min), “Tomorrow”, “Skip this time”. Do not start the retro itself "
              "without their consent."},

    # zaloz.py, dopisz_metryki.py
    "zal_nie_repo": {"pl": "{sciezka} nie jest w repozytorium git; tryb projektu wymaga repo.",
                     "en": "{sciezka} is not in a git repository; project mode needs a repo."},
    "zal_git_init_blad": {"pl": "git init nieudany: {blad}", "en": "git init failed: {blad}"},
    "zal_wskaznik": {"pl": "Wskaźnik {wskaznik} prowadzi do {obecny}; nie zmieniono (użyj --nadpisz-wskaznik).",
                     "en": "Pointer {wskaznik} leads to {obecny}; not changed (use --nadpisz-wskaznik)."},
    "zal_brak_szablonow": {"pl": "Brak szablonów dla języka `{jezyk}`: użyto `{zapas}`; nagłówki przetłumacz przy wypełnianiu.",
                           "en": "No templates for language `{jezyk}`: used `{zapas}`; translate the headings when filling them in."},
    "dop_brak_katalogu": {"pl": "Nie znaleziono katalogu roboczego retro (--katalog).",
                          "en": "No retro working directory found (--katalog)."},
    "dop_brak_metryk": {"pl": "Brak dane/sygnaly-*/metryki.json: uruchom najpierw sygnaly.py albo podaj --metryki.",
                        "en": "No dane/sygnaly-*/metryki.json: run sygnaly.py first or pass --metryki."},
}


def ustaw(jezyk) -> str:
    """Ustawia język komunikatów: kod albo słownik konfiguracji z polem `jezyk`. Zwraca kod."""
    global _jezyk
    if isinstance(jezyk, dict):
        jezyk = jezyk.get("jezyk")
    _jezyk = str(jezyk or "pl").strip().lower() or "pl"
    return _jezyk


def jezyk() -> str:
    return _jezyk


def jezyk_tekstow(kod: str = None) -> str:
    """Język, w którym są teksty i szablony dla `kod` (obsługiwany albo zapasowy)."""
    kod = kod or _jezyk
    return kod if kod in JEZYKI else ZAPASOWY


def t(klucz: str, **pola) -> str:
    wpis = TEKSTY[klucz]
    tekst = wpis.get(jezyk_tekstow()) or wpis[ZAPASOWY]
    return tekst.format(**pola)


def wszystkie(klucz: str) -> tuple:
    """Wszystkie wersje językowe tekstu (rozpoznawanie własnych uwag skryptu w danych z innego języka)."""
    return tuple(TEKSTY[klucz].values())
