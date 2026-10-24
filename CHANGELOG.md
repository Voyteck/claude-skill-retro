# Zmiany

## 0.4.0 · 2026-10-24

Dane do reguł doboru agenta: który agent, na jakim modelu i poziomie rozumowania robi jakie zadanie. Jakość pisania
ocenia się teraz razem z ceną: czy lepszy model albo wyższy poziom rozumowania oszczędza tyle poprawek, że opłaca się
zamiast tańszego.

- **Poziom rozumowania w danych.** Pole `effort` rekordów asystenta (low…max) trafia do wywołań, archiwum tokenów
  i wyniku `zbierz_liczby.py` (`eff`) oraz do zdarzeń agentów (`effort_zadany` z wywołania, najczęstszy poziom
  z transkrypcji podagenta). Tabela kosztu wg roli ma wiersze „rola · model · poziom”; nowa metryka
  `koszt_wg_poziomu`.
- **Koszt i jakość na PR wg konfiguracji implementatora.** Koszt każdego podagenta (z sum tokenów jego transkrypcji,
  w cenach bieżących modeli rodziny) dzielony na PR, nad którymi pracował; PR łączone z rundami poprawek z GitHuba
  po (repo, numer), a ze źródeł zdalnych po jednoznacznym numerze. Tabela wg „model · poziom” pierwszego
  implementatora i rozmiaru PR (S/M/L z dodanych i usuniętych linii, progi `pr_progi_rozmiaru`): PR, odsetek
  z poprawką, rundy, koszt implementacji i kontroli na PR, **koszt na PR** (= oczekiwany koszt zaakceptowanego PR,
  bo zawiera rundy poprawek z ich częstością) i na 100 linii. PR implementowane w sesji głównej mają tylko jakość.
- **Obecna konfiguracja agentów** z `.claude/agents/*.md` repozytoriów okna i `~/.claude/agents` (model, poziom,
  rola), żeby propozycja reguły wskazywała plik do zmiany.
- **Sekcja 2a** (szablony pl/en, `SKILL.md`): tabela „Reguły doboru agenta” (zadanie · teraz · proponowane · dane ·
  miara), porównanie konfiguracji po koszcie na PR w tej samej roli i rozmiarze, eksperyment zamiast reguły przy
  < 5 PR.
- **Nowe kolumny `metryki.csv`** (na końcu): `pr_powiazane`, `koszt_na_pr_usd`, `koszt_na_pr_wg_konfiguracji`,
  `koszt_wg_poziomu`; `koszt_na_pr_usd` dochodzi do porównania z poprzednimi retro.
- **Poprawka:** tokeny podagenta liczone z rekordu z pełnym `usage` (wcześniej z pierwszego, częściowego rekordu
  strumienia), zapis cache rozdzielony na 5 min i 1 h.

## 0.3.0 · 2026-10-24

Tokeny i efektywność pisania w każdym retro: co było lepsze, co gorsze wobec 2–3 poprzednich retro, ile razy praca
wracała od przeglądu i CI do implementacji i jak to zależy od modelu, który programował.

- **Nowa sekcja podsumowania „Tokeny i efektywność pisania”** (PL/EN, `scripts/efektywnosc.py`):
  - porównanie wskaźników tokenów i poprawek z 3 ostatnimi wierszami `metryki.csv`, ze strzałkami lepiej/gorzej;
  - koszt wg roli agenta (sesja główna, implementacja, przegląd, CI, architekt, inne podagenty) i rodziny modelu,
    tydzień po tygodniu, w cenach bieżących modeli rodziny, osobno dla każdego źródła trendu;
  - rundy poprawek w scalonych PR z GitHuba (`gh api graphql`): paczka commitów po przerwie > 20 min to runda,
    model autora ze stopki `Co-Authored-By: Claude <Model>`; tabele wg tygodnia, modelu autora, tygodnia × modelu
    i „kto pisał poprawki”;
  - powroty od przeglądu i CI w transkrypcjach: implementator uruchomiony albo kontynuowany na tym samym PR po
    negatywnym werdykcie przeglądu albo czerwonym CI, wg typu i modelu implementatora.
- **Role agentów** z pola `role_agentow` konfiguracji (wzorce typu podagenta; domyślne role w
  `efektywnosc.ROLE_DOMYSLNE`). Nowe pola: `efektywnosc_tygodnie`, `pr_przerwa_rundy_min`, `pr_max_commitow`,
  `pr_pomin_galezie`.
- **`scripts/zdarzenia_agentow.py`**: samodzielny skrypt (biblioteka standardowa) wyciągający z transkrypcji same
  liczby i etykiety pracy podagentów (start, kontynuacja, raport, werdykt, wynik CI, numery PR, tokeny). Lokalnie
  wywołuje go `sygnaly.py`; dla innej maszyny wpis `zrodla_zdalne` dostaje pola `zdarzenia_polecenie` albo
  `zdarzenia_plik` (jedna próba, bez ponawiania).
- **Archiwum tokenów** zapisuje typ podagenta (`agent`), jak archiwa źródeł zdalnych; starsze wpisy bez typu liczą
  się jako „inne podagenty”.
- **Nowe kolumny `metryki.csv`** (na końcu): `pr_analizowane`, `pr_z_poprawka_proc`, `rundy_na_pr`, `pr_wg_modelu`,
  `pr_z_poprawka_proc_wg_modelu`, `powroty_przeglad`, `powroty_ci`, `koszt_implementacji_proc_wg_modelu`.
- **Szablony retro** (`assets/pl`, `assets/en`): obowiązkowa sekcja „2a. Tokeny i efektywność pisania” (porównanie
  z 2–3 poprzednimi retro, lepiej/gorzej z liczbami, efektywność wg modelu implementatora, 2–3 sugestie z efektem
  i miarą); `SKILL.md` opisuje, jak ją wypełnić. Ograniczenia pomiaru: `references/sygnaly.md`.
## 0.2.2 · 2026-10-24

Poprawka z retro autora (R04): wiadomości właściciela poprzedzone przypomnieniem systemowym.

- **Wiadomość właściciela po bloku `<system-reminder>` jest liczona.** Aplikacja Claude dokleja na początek
  wiadomości właściciela przypomnienia (np. „Linked sessions now…”, gdy sesja ma sesje poboczne), a `sygnaly.py`
  i `zbierz_liczby.py` odrzucały każdy tekst zaczynający się od `<system-reminder`. Teraz początkowe bloki są
  zdejmowane (nowa funkcja `sygnaly.zdejmij_przypomnienia`, wspólna z przyczynami wybudzeń) i dopiero reszta jest
  rozpoznawana; oś czasu pokazuje wiadomość bez bloku. Sam blok bez reszty nadal nie jest wiadomością, a reszta
  będąca powiadomieniem (`<side-sessions-event>`, „The app was quit…”, `<cross-session-message>`, brief innej
  sesji) też nie: oba skrypty mają teraz tę samą listę takich początków.
- **Uwaga do porównań:** od tej wersji `wiad_wlasciciela` (i to, co z niej wynika: `koszt_na_wiadomosc_usd`,
  `koszt_na_wiad` w trendzie, `owner` w archiwum tokenów) rośnie w sesjach z sesjami pobocznymi, więc nie jest
  porównywalne z retro sprzed 0.2.2. Na transkrypcjach autora: 183 → 219 wiadomości (+20%). Archiwum trendu łączy
  stare i nowe odczyty, więc tygodnie, których transkrypcje jeszcze istnieją, zostaną przeliczone w górę przy
  najbliższym retro; starsze zostają zaniżone.

## 0.2.1 · 2026-10-24

Trzy poprawki z retro autora (R04): dokładniejsze sygnały tam, gdzie wnioski z retro okazały się chybione.

- **`pyt_fakt` tylko dla znacznika na początku pytania.** Pytanie liczy się jako „fakt”, gdy jego treść zaczyna
  się (po ewentualnych odstępach) od `[fakt]` albo `[fact]`. Wcześniej wystarczyło to słowo w dowolnym miejscu, więc
  decyzja, która cytowała „[fakt]” w treści, trafiała do faktów zamiast do `inna`. Rozpoznawanie: nowa funkcja
  `teksty.pytanie_o_fakt`.
- **Wybudzenia z podziałem na przyczynę.** Przyczyną jest pierwsze wejście sesji po przerwie: wiadomość właściciela,
  zadanie lub podagent w tle (`<task-notification>`, `queue-operation`, „[Subagent hand-back]”), inna sesja (`peer`,
  `<agent-message>`, `<cross-session-message>`, `<side-sessions-event>`, przypomnienie systemowe o sesjach) albo
  inne (np. wynik narzędzia po długim czekaniu lub ponowieniach po błędach API). Przypomnienia systemowe doklejane
  przez aplikację na początku wiadomości są przy tym pomijane. Podsumowanie podaje przyczynę przy każdym
  wybudzeniu i zestawienie; nowe metryki `wybudzenia_wlasciciel`, `wybudzenia_tlo`, `wybudzenia_sesja`,
  `wybudzenia_inne` (suma = `wybudzenia`) są dopisane na końcu kolumn `metryki.csv`. Hook na wiadomość właściciela
  (`UserPromptSubmit`) leczy tylko pierwszą przyczynę; raport pokazuje, ile wybudzeń jest poza jego zasięgiem.
- **Trend: tydzień niezakończony obok porównania.** Tabela trendu ma ostatnią kolumnę z bieżącym tygodniem (jeśli
  była w nim aktywność) i strzałką wobec mediany ostatnich tygodni, żeby świeża poprawka albo pogorszenie były
  widoczne od razu, a strzałka porównania nie była brana za stan po poprawce. Sumy tygodnia (koszt tygodnia, koszt
  wybudzeń) jeszcze rosną, więc dostają tylko „↑”. Tydzień nadal nie wchodzi do porównania.

## 0.2.0 · 2026-10-22

Wielojęzyczność: plugin nadaje się dla osób, które nie piszą po polsku.

- **Pole `jezyk`** w `konfiguracja.json` (`pl`, `en`; inne kody: szablony i komunikaty skryptów po angielsku,
  Claude pisze w danym języku). Brak pola = `pl`, więc katalogi sprzed 0.2.0 działają bez zmian.
  `zaloz.py --jezyk KOD` (domyślnie `en`); retro zero pyta o język jako pierwsze.
- **Szablony** w `assets/pl/` i `assets/en/` (te same nazwy plików); `metryki-naglowek.csv` zostaje w `assets/`.
- **Raporty skryptów** (podsumowanie, osie czasu, przypomnienie) w języku z konfiguracji; teksty w nowym
  `scripts/teksty.py` (nowy język = kod w `JEZYKI` i tłumaczenia; test pilnuje kompletności).
- **„Możliwa korekta”** liczona słowami języka z konfiguracji plus angielskimi (lista angielska rozszerzona
  o „wait”, „not what”, „I said”, „I asked”, „you forgot”). Przy `jezyk=en` polskie słowa nie są liczone.
- **`wiad_po_20`** liczone z pory dnia, nie z polskiej etykiety „noc”.
- **Statusy i znaczniki niezależne od języka:** retro zakończone to `zakończone`, `zakonczone`, `completed`, `done`
  albo `closed`; pytanie o fakt to `[fakt]` albo `[fact]`.
- **Opcja rekomendowana** rozpoznawana w wielu językach (m.in. rekomendowane, recommended, recomendado, recommandé,
  empfohlen, raccomandato, aanbevolen).
- **Dokumentacja po angielsku:** `SKILL.md`, `references/`, `README.md`; polska wersja README w `README.pl.md`.
  Identyfikatory (nazwy plików, klucze konfiguracji, kolumny CSV, argumenty) zostają polskie; słowniczek
  w `references/konfiguracja.md`.
- Usunięte odniesienia do projektów i retro autora z dokumentacji skillu.

## 0.1.5 · 2026-10-20

- **Źródła zdalne trendu tokenów** (`zrodla_zdalne`, domyślnie brak): druga maszyna z Claude Code, np. sandbox.
  Dane można wziąć na dwa sposoby:
  - `polecenie` (np. `ssh -T host python3 -`, także z `docker exec` w środku): skrypt podaje na stdin nowy
    samodzielny `scripts/zbierz_liczby.py`, który wypisuje same liczby z transkrypcji tamtej maszyny, bez treści
    rozmów, i niczego tam nie zapisuje;
  - `plik`: ten sam wynik zapisany wcześniej przez właściciela.

  Na każde źródło przypada jedna próba, bez ponawiania; gdy się nie uda, podsumowanie podaje przyczynę, a skrypt
  liczy dalej. Każde źródło ma osobne archiwum `dane/tokeny-archiwum-<nazwa>.json` i wiersze `zrodlo=<nazwa>`
  w `tokeny-tydzien.csv`. Format jest zgodny z ręcznym odczytem sandboksa (`sandbox-liczby.json`,
  `tokeny-archiwum-sandbox.json`). `--bez-zdalnych` pomija źródła zdalne w danym przebiegu.
- **Poprawka 0.1.4:** zapis trendu sklejał wiersze innych źródeł, które miały ten sam tydzień (np. dwa okna
  `sandbox-pomiar` z 09-26), i czyścił kolumny, których skrypt nie liczy (`*_sygnaly`, `pokrycie_wiad_proc`), oraz
  ręczne uwagi w `pokrycie`. Teraz wiersze obcych źródeł zostają dosłownie, a w wierszach skryptu zostają nieznane
  kolumny i cudze uwagi.
- Źródło z kilkoma wierszami na tydzień (pomiary okienne) nie dostaje tabeli trendu.
- Wiadomości właściciela nie obejmują promptów `claude -p` (entrypoint `sdk-cli`).
- `SKILL.md`, krok 1: gdy źródła zdalnego nie da się odczytać, Claude nie ponawia połączenia, tylko podaje
  użytkownikowi polecenie do uruchomienia u siebie.
- Testy: 40 (było 35).

## 0.1.4 · 2026-10-20

Decyzje właściciela z R03 (sekcja 10), po wydaniu 0.1.3.

- **Trend tokenów tydzień po tygodniu.** `sygnaly.py` dopisuje do `tokeny-tydzien.csv` w katalogu roboczym
  (commitowany) wiersz na tydzień, bez duplikatów: tydzień niepełny jest nadpisywany. Kluczem jest para (tydzień,
  źródło), więc skrypt pisze tylko `zrodlo=lokalne`, a wiersze innych źródeł (np. sandbox) zostają nietknięte.
  Kolumny są zgodne z ręcznym `tokeny-tydzien-lokalne.csv` z R03. Podsumowanie ma sekcję „Trend tokenów”:
  ostatnie 4 tygodnie wobec mediany 8 wcześniejszych, ze strzałkami i listą wskaźników, które się pogarszają.
- **Archiwum liczb** `dane/tokeny-archiwum.json`: wywołania, czasy wiadomości i kompaktów, `cost-state`, bez treści
  rozmów. Chroni trend przed `cleanupPeriodDays` (w R03 zniknęły tak sesje z 09-19). Format jest zgodny z archiwum
  założonym ręcznie w R03. `--bez-trendu` pomija archiwum i trend.
- Cennik i liczenie kosztu wydzielone do `scripts/tokeny.py`. W cenniku doszło `rodziny_biezace`, potrzebne do
  kolumny „koszt w cenach bieżących modeli”.
- Wiadomości właściciela nie obejmują już briefów innych sesji („Background (from the session…”),
  `<system-reminder>` ani `<cross-session-message>`.
- `SKILL.md`:
  - krok 1: czytanie trendu;
  - krok 4: „Zrobić teraz” od razu jako karta z przejściem do folderu projektu w briefie, bo w turze wywołanej
    zdarzeniem automatycznym aplikacja pozwala tylko zaproponować kartę, a karta nie wskazuje folderu;
  - krok 5: commit `tokeny-tydzien.csv`.
- Nie ma jeszcze źródła zdalnego (sandbox przez ssh, opcjonalne pole konfiguracji): to następny krok.
- Testy: 35 (było 30).

## 0.1.3 · 2026-10-20

Propozycje z retro R02 (sekcja 10) i R03 (sekcje 2a, 7, 10).

- **Okno od godziny commita poprzedniego retro**, nie od północy: wiadomości, pytania, błędy, commity, PR-y, CI
  i tokeny z sesji tamtego retro sprzed jego zakończenia nie zawyżają nowego okna (R02: 52 pytania zamiast 24).
  `--od` przyjmuje też godzinę (`2026-10-17T20:52`), `--od-poczatku-dnia` wraca do starego zachowania.
- **Klasa `fakt`** dla pytań z „[fakt]” (hook Z-004 je dopuszcza bez rekomendacji): nie wchodzą już do
  `bez_rekomendacji`, a odpowiedź własnym tekstem nie jest liczona jako `wlasna`. Kolumna `pyt_fakt`.
- **Tokeny i koszt** liczone w skrypcie zamiast ręcznie przez podagentów (R03 2a): wywołania deduplikowane po
  `message.id`, razem z transkrypcjami podagentów; koszt w cenach API jako miara względna z cennikiem
  w `references/cennik.json` (nadpisania w polu `cennik` konfiguracji); koszt na wiadomość; mediana kontekstu sesji
  głównej i odsetek wywołań > 200k; udział podagentów w koszcie i udział Opusa w koszcie podagentów; wybudzenia
  (zapis cache > 50k po przerwie > 1 h) z listą; kontekst startowy sesji; najdroższe sesje; koszt w tabelach
  projektów i sesji. Na danych R02 i R03 wyniki zgadzają się z ręczną analizą R03 (np. wybudzenia R02 $9,10).
- **Praca bez lokalnych sesji:** commity i PR-y bez zapisu transkrypcji sesji repo w ±30 min (`commity_bez_sesji`,
  `pr_bez_sesji`) i uwaga w podsumowaniu (w jednym z repozytoriów 190 z 205 commitów). Pole `transkrypcje_dodatkowe`
  dołącza transkrypcje skopiowane z innej maszyny.
- **Linie reguł:** pole `katalogi_regul_osobno` (np. `repo-roots/` z kopiami `CLAUDE.md` dla przyszłych repo)
  liczy takie katalogi osobno (`claude_md_linie_osobno`); podsumowanie podpowiada kandydatów (≥ 3 zagnieżdżone
  `CLAUDE.md` w jednym katalogu).
- **`metryki.csv` zgodnie wstecz:** nowe kolumny na końcu nagłówka, za `zobowiazania_aktywne` (także
  `pyt_bez_wyboru`, dotąd tylko w `metryki.json`). Nowy skrypt `dopisz_metryki.py` dopisuje wiersz retro
  i rozszerza nagłówek starszego pliku; ponowne uruchomienie zastępuje wiersz.
- `SKILL.md`: przed werdyktem „martwe/porzucić” pytanie, czy ktoś tego używa; krok 1 korzysta z metryk tokenów;
  krok 5 dopisuje metryki skryptem.
- Testy: 30 (było 21).

## 0.1.2 · 2026-10-10

Poprawki po pierwszym retro na pełnym koncie (R01: 43 sesje, 6 projektów).

- **Sekrety nie trafiają do wyciągów.** `sygnaly.py` zamazuje przed zapisem ciągi wyglądające na sekrety
  (`gh secret set … --body`, `NAZWA_KEY=…`, `Bearer …`, znane przedrostki kluczy, klucze prywatne, długie ciągi
  liter i cyfr); zostawia hashe commitów i digesty obrazów. W R01 klucz wklejony do rozmowy trafił do `dane/`
  i do kontekstu podagentów.
- **Wiadomości wysłane w trakcie pracy Claude'a są liczone.** Były zapisane tylko jako `queued_command` i ginęły
  z osi czasu (w jednej sesji 8 wiadomości, w tym kluczowe dla kosztów). Oś czasu oznacza je „w trakcie pracy
  Claude'a”.
- **Sesje uruchomione w scratchpadzie** (testy `claude -p`) są pomijane, bo zawyżały liczbę sesji i wiadomości.
- **Pliki reguł:** liczone są śledzone `CLAUDE.md` na dowolnej głębokości repo; podsumowanie pokazuje, o ile
  commitów checkout jest za zdalną gałęzią (wtedy reguły na dysku są nieaktualne), i wymienia projekty z pamięcią
  bez lokalnej sesji w oknie.
- **Retencja:** ostrzeżenie, gdy okno retro sięga dalej niż `cleanupPeriodDays`.
- `SKILL.md`: na Windows skrypty uruchamia się przez `py`, gdy `python` to atrapa ze Sklepu Microsoft; przy
  ponad 8 pozycjach „czeka na użytkownika” pytania łączy się per projekt, sprawy bezpieczeństwa osobno.
- Testy: 21 (było 14).

## 0.1.1 · 2026-10-09

- Przypomnienie i README katalogu roboczego podają krótkie polecenie `/retro`. Sprawdzone w Claude Code
  2.1.293 (Windows): skill pluginu odpowiada na samą nazwę, gdy żadne inne polecenie jej nie zajmuje; pełna
  nazwa `/retro:retro` działa zawsze.

## 0.1.0 · 2026-10-09

Pierwsza wersja uniwersalna, wydzielona z prywatnego skillu retro po retro zero (R00).

- Tryb konta (wszystkie projekty z transkrypcji) i tryb projektu (`.retro/` w repo).
- Projekty i repozytoria wykrywane przez git z katalogów sesji; poprawki nazw w konfiguracji.
- Procedura z R00: jedno pytanie = jedna decyzja, sekcja „Czeka na użytkownika”, `nauki.md` na wiedzę
  przekrojową, zasada „mechanizm zamiast tekstu”.
- Klasa odpowiedzi „bez wyboru” (`[No preference]`).
- Kalendarz dni roboczych: polski albo sam weekend, plus własne dni wolne.
- Hook przypomnienia w pluginie (bash z wykrywaniem Pythona).
- Poprawka nazwy projektu w konfiguracji zmienia tylko nazwę; repo nadal wykrywane przez git.
- Testy na sztucznych transkrypcjach (14).
