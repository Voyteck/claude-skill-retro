---
name: retro
description: Retrospektywa sposobu pracy z Claude Code w stylu Agile (użytkownik + Claude + podagenci), zwykle co 2 dni robocze. Rozlicza zobowiązania z poprzednich retro (czy były przestrzegane i czy miały sens), zbiera dowody z transkrypcji Claude Code, gita i GitHuba, ocenia co działało i co nie (także po stronie użytkownika), proponuje najwyżej 5 zmian do jego decyzji i wdraża przyjęte. Przy pierwszym użyciu zakłada katalog roboczy (całe konto albo jeden projekt). Użyj, gdy użytkownik prosi o retro, retrospektywę, lessons learned, przegląd nauk, „co robimy dobrze, a co źle”, „czy trzymamy się ustaleń”, continuous improvement, albo gdy przypomnienie o zaległym retro dostało jego zgodę.
---

# Retro

Cel: domknięta pętla **zobowiązanie → przestrzeganie → efekt → decyzja**, a nie lista spostrzeżeń. Każde retro
zaczyna się od rozliczenia tego, co ustalono wcześniej.

## Miejsca

- **Skill:** `${CLAUDE_SKILL_DIR}` (`scripts/`, `assets/`, `references/`). Skrypty uruchamiasz
  `python "${CLAUDE_SKILL_DIR}/scripts/<skrypt>.py"` (albo `python3`; Python ≥ 3.8, tylko biblioteka standardowa).
  Na Windows `python` i `python3` bywają atrapami ze Sklepu Microsoft („nie znaleziono Python”): użyj wtedy `py`.
- **Katalog roboczy** (stan między retro, zawsze poza skillem):
  - tryb **konta**: wszystkie projekty z transkrypcji na tym koncie; katalog wskazuje `~/.claude/retro.json`;
  - tryb **projektu**: jedno repo; katalog `<repo>/.retro/`, commitowany z projektem, wspólny dla zespołu.

  Zawartość: `konfiguracja.json`, `retro/RNN-RRRR-MM-DD.md`, `zobowiazania.md` (rejestr), `metryki.csv`,
  `nauki.md` (tryb konta), `dane/` (wyciągi z transkrypcji, poza gitem).
- Skrypty: `wspolne.py` (rozpoznanie stanu), `zaloz.py` (zakładanie katalogu), `sygnaly.py` (dowody z okna),
  `tokeny.py` (cennik, archiwum i trend tokenów; używa go `sygnaly.py`), `zbierz_liczby.py` (liczby z transkrypcji
  innej maszyny dla trendu), `dopisz_metryki.py` (wiersz `metryki.csv`),
  `przypomnienie.py` (hook przypomnienia). Pola konfiguracji:
  `references/konfiguracja.md`. Znaczenie metryk i ich ograniczenia: `references/sygnaly.md`; ceny do metryk
  kosztu: `references/cennik.json`.

## Zasady stałe

1. **Dowód albo nic.** Każde „dobrze”, „źle” i ocena przestrzegania wskazuje dowód: `MM-DD HH:MM` + 8 znaków id
   sesji (z osi czasu w `dane/sygnaly-*/<projekt>.md`), numer PR, hash commitu albo plik.
2. **Oceniasz też siebie, więc bez laurki.** Najpierw szukaj złamań zobowiązań, potem potwierdzeń. Przy
   „przestrzegane” podaj liczbę okazji i złamań, nie przymiotnik.
3. **Strona użytkownika szczerze**, gdy `ocena_wlasciciela` w konfiguracji jest włączona: jego decyzje i nawyki
   oceniasz jak pracę Claude'a, w kategoriach kosztu i efektu (czas, przerwane prace, rundy poprawek), nie osoby.
4. **Mniej reguł, nie więcej.** Najwyżej 5 nowych zobowiązań na retro. Przy ponad 10 aktywnych retro musi
   zaproponować co najmniej jedno utrwalenie albo porzucenie. Każda rekomendacja mówi, co zastępuje lub skraca.
5. **Mechanizm zamiast tekstu.** Reguły z mechanizmem (test, hook, ochrona gałęzi, szablon, przypięty model
   agenta) są przestrzegane; reguły tylko w tekście, wymagające nawyku, zwykle umierają. Proponując zmianę,
   najpierw szukaj mechanizmu; samą regułę w tekście proponuj, gdy mechanizmu nie ma.
6. **Decyduje użytkownik.** Propozycje stają się zobowiązaniami dopiero po jego akceptacji. Pytaj narzędziem
   AskUserQuestion (jeśli jest dostępne; inaczej numerowaną listą w wiadomości), rekomendowana opcja pierwsza
   z dopiskiem „(rekomendowane)”. **Jedno pytanie = jedna niezależna decyzja.** Treść propozycji i ewentualny
   krok do wykonania wpisz w samo pytanie, bo tekst nad widżetem bywa niewidoczny.
7. **Retro nie zmienia kodu produktów** i nie uruchamia ciężkich testów. Zmienia reguły (CLAUDE.md, pamięć,
   rejestr, `nauki.md`) i tylko po decyzji użytkownika.
8. Po polsku, bez żargonu tam, gdzie jest polskie słowo.

## Krok 0. Rozpoznanie i pierwsze uruchomienie

1. `python "${CLAUDE_SKILL_DIR}/scripts/wspolne.py"` wypisuje JSON: katalog roboczy, tryb, konfigurację,
   ostatnie zakończone retro, następny numer.
2. **Brak katalogu** (`katalog_roboczy: null`) = pierwsze uruchomienie. Zadaj osobne pytania:
   - tryb: „Całe konto (rekomendowane, gdy jedna osoba pracuje w wielu projektach)” / „Ten projekt (retro
     w repo, wspólne dla zespołu)”;
   - w trybie konta katalog: `~/retro` (rekomendowane) / inny;
   - ocena strony użytkownika: „Tak, szczerze (rekomendowane)” / „Tylko praca Claude'a i agentów”;
   - kalendarz dni roboczych: „Polski (rekomendowane)” / „Sam weekend”.

   Potem `python "${CLAUDE_SKILL_DIR}/scripts/zaloz.py" --tryb konto --katalog <katalog> [--kalendarz brak]
   [--bez-oceny-wlasciciela]` albo `--tryb projekt --repo <repo>`. Pokaż, co powstało. Jeśli skill nie jest
   zainstalowany jako plugin, przypomnienie nie działa samo: zaproponuj hook według `references/konfiguracja.md`,
   sekcja „Przypomnienie bez pluginu”.
3. Tryb konta: sesja powinna pracować w katalogu roboczym (przenieś ją narzędziem zmiany katalogu, jeśli jest;
   inaczej używaj ścieżek bezwzględnych). Tryb projektu: sesja w repo projektu.
4. Numer `N` = `nastepny_numer`. Plik `retro/RNN-RRRR-MM-DD.md` z `assets/szablon-retro.md`,
   `**Status:** szkic`. Jeśli istnieje niezakończony szkic, zapytaj: dokończyć go czy zastąpić.
5. Okno: od dnia ostatniego **zakończonego** retro (włącznie) do dziś. `sygnaly.py` sam zaczyna je od godziny
   commita, który zakończył tamto retro, więc zdarzenia sprzed niego nie liczą się do rozliczenia. Argumenty
   skillu („tylko projekt X”, „od 2026-10-06”) zawężają okno lub zakres.

**Retro zero** (brak zakończonych retro, pusty rejestr): okno od najstarszej transkrypcji. Zamiast rozliczenia
rejestru zrób bilans dotychczasowych nauk: wpisy `feedback` w pamięci projektów
(`~/.claude/projects/*/memory/`), globalny `~/.claude/CLAUDE.md` i sekcje o pracy z Claude'em w CLAUDE.md
repozytoriów. Traktuj je jak niejawne zobowiązania: przestrzegane? z efektem? duplikaty między projektami?
sprzeczne? martwe? Wynik to pierwszy rejestr (najwyżej 10 aktywnych) do akceptacji użytkownika.

## Krok 1. Dane

```
python "${CLAUDE_SKILL_DIR}/scripts/sygnaly.py" --od RRRR-MM-DD
```

Wynik w `<katalog roboczy>/dane/sygnaly-<od>_<do>/`: `podsumowanie.md`, `metryki.json`, `<projekt>.md` (oś
czasu). Przeczytaj podsumowanie i metryki, porównaj z `metryki.csv`. Klasy odpowiedzi na pytania i ograniczenia
liczb: `references/sygnaly.md`. „[K?]” to heurystyka, nie dowód.

Tokeny i koszt lokalnych sesji liczy skrypt (sekcja „Tokeny i koszt” podsumowania: koszt w cenach API jako miara
względna, koszt na wiadomość, kontekst, podagenci, wybudzenia, kontekst startowy); ręcznej analizy tokenów nie rób.
Do trendu bierz `koszt_na_wiadomosc_usd`, `kontekst_mediana`, `kontekst_ponad_200k_proc`, `podagenci_opus_koszt_proc`,
`wybudzenia` i `kontekst_startowy_mediana`; najdroższe sesje i wybudzenia z listy w podsumowaniu to dowody do
sekcji „co nie działało”. Pracy w sandboksie i chmurze lokalne tokeny nie obejmują: gdy w repo są rekordy zużycia
z tamtych środowisk (np. ze skillu `claude-usage-report`), weź z nich koszt na scalony PR.

Przeczytaj też sekcję „Trend tokenów”: tydzień po tygodniu z `tokeny-tydzien.csv` (skrypt dopisuje do niego
kolejne tygodnie i nadpisuje tydzień niepełny), ostatnie 4 tygodnie wobec mediany 8 wcześniejszych. Wskaźnik
oznaczony **↑ pogorszenie** wpisz do sekcji „co nie działało” z liczbami z tabeli i poszukaj przyczyny w najdroższych
sesjach okna; „za mało danych” nie jest sygnałem. Wiersze innych źródeł (np. `zrodlo=sandbox`) mają własną
tabelę; nie sumuj ich z lokalnymi. Źródło zdalne z konfiguracji (`zrodla_zdalne`) skrypt odczytuje raz; gdy
podsumowanie pokazuje „brak odczytu”, nie ponawiaj połączenia ani nie sonduj maszyny. Podaj użytkownikowi gotowe
polecenie do uruchomienia u siebie (`references/sygnaly.md`, „Źródła zdalne”: wynik do pliku i pole `plik`) i
licz trend z tego, co jest w archiwum.

Podsumowanie zawiera uwagi o danych; uwzględnij je, zanim zacytujesz liczby: okno dłuższe niż retencja
transkrypcji, checkout repo w tyle za zdalną gałęzią (reguły na dysku nieaktualne), projekty z pamięcią bez sesji
w oknie, repo z commitami bez lokalnych sesji (sandbox, chmura: liczby na wiadomość i sesję tej pracy nie widzą),
katalogi z kopiami `CLAUDE.md` (kandydaci do `katalogi_regul_osobno`; dopisanie to decyzja użytkownika), modele
bez ceny w cenniku. Sekrety w osiach czasu są zamazywane (`[zamazane]`), ale to heurystyka: gdy mimo to zobaczysz klucz albo
hasło, nie przepisuj go do pliku retro ani do zadań dla podagentów, tylko zgłoś w sekcji 8a jako sprawę do rotacji.

## Krok 2. Analiza

- **Małe okno** (do ~40 wiadomości użytkownika łącznie): analizuj sam.
- **Większe:** podagenci `general-purpose` z jawnym modelem `model_podagentow` z konfiguracji, równolegle,
  jeden na projekt z ruchem plus jeden przekrojowy (współpraca, strona użytkownika, sprzeczności między
  projektami). Każdy dostaje ścieżkę osi czasu projektu, `zobowiazania.md`, pliki reguł projektu, sekcję
  „Zasady stałe” i zadanie:
  1. dla każdego aktywnego zobowiązania: okazje, złamania, dowody, czy dało efekt;
  2. co działało / co nie działało, z dowodami i przyczyną;
  3. obserwacje strony użytkownika (jeśli ocena włączona);
  4. sprzeczne i martwe reguły;
  5. najwyżej 3 kandydatów na rekomendacje, każdy z sygnałem przestrzegania i mechanizmem, jeśli jest.

  Podagent zapisuje analizę do `dane/sygnaly-…/analiza-<zakres>.md` i zwraca ≤300 słów. Pełną transkrypcję
  (`~/.claude/projects/*/<sesja>.jsonl`) może przeszukiwać `grep` po id sesji i czasie, nie wczytuje jej całej.
  Pytania podagentów wracają w raporcie; zadajesz je użytkownikowi.

## Krok 3. Synteza

Wypełnij plik retro wg szablonu. Rozliczenie zobowiązań:

| pole | wartości |
|---|---|
| przestrzegane | tak / częściowo (x z y okazji) / nie / brak okazji |
| sens | tak / nie / za wcześnie (za mało okazji) |
| werdykt | utrzymać / zmienić / utrwalić / porzucić |

- **utrwalić** = przestrzegane bez złamań w 3 kolejnych retro → zostaje w pliku reguł, rejestr przestaje je
  śledzić (sprawdzenie wyrywkowe raz na 5 retro);
- **porzucić** = brak efektu albo koszt większy niż zysk → usuń też z plików reguł;
- **zmienić** = idea dobra, forma nie działa → nowe zobowiązanie zastępuje stare.

Zanim uznasz coś za martwe albo zaproponujesz „porzucić” (regułę, katalog, skrypt, hook, stronę), zapytaj
użytkownika, czy ktoś tego używa: brak śladu w transkrypcjach nie znaczy, że nikt tego nie używa (praca w chmurze,
inni ludzie, rzadkie użycie; przykład z R01: katalog `site/`). Pytaj w kroku 4 razem z werdyktem albo
wcześniej, gdy od odpowiedzi zależy analiza.

**Czeka na użytkownika** (sekcja 8a szablonu). Zbierz z dowodem i datą „od”:
- pytania odłożone w oknie (klasa „odłożone” w osiach czasu), które nie wróciły;
- PR-y otwarte dłużej niż 2 dni robocze (`gh pr list` w repozytoriach z podsumowania) i gałęzie niewypchnięte
  (`git log --branches --not --remotes`);
- notatki przekazania (`HANDOFF*`, wpisy pamięci „do zrobienia”) bez sesji w projekcie od ponad 10 dni roboczych;
- otwarte pytania z plików `rejestry_pytan` z konfiguracji, starsze niż 30 dni;
- pozycje z sekcji 8a poprzedniego retro, których nie zamknięto.

Retro samo tych spraw nie wykonuje; o każdą pozycję pytasz w kroku 4.

## Krok 4. Decyzje użytkownika

Do 4 pytań na wywołanie, jedno pytanie = jedna niezależna decyzja (łącz tylko pomysły od siebie zależne).
Kolejność: rekomendacje i zmiany statusu, potem sprzątanie reguł, na końcu „czeka na użytkownika”.
- utrzymanie zobowiązania bez zmiany statusu: `Utrzymaj (rekomendowane)` / `Zmień: …` / `Porzuć`;
- werdykt zmieniający status, nowa rekomendacja, usunięcie z reguł: `Przyjmij (rekomendowane)` / `Zmień: …` / `Odrzuć`;
- pozycja „czeka na użytkownika”: `Zrobić teraz (w sesji projektu)` / `Zamknąć` / `Odłożyć do <data>`.
  „Zrobić teraz” = zadanie dla sesji projektu z pełnym kontekstem, nie praca retro. Gdy jest narzędzie do
  zakładania sesji (np. `start_session`, `spawn_task`), od razu zaproponuj je kartą (propozycja, którą użytkownik
  uruchamia jednym kliknięciem), nie czekaj na osobną zgodę na start: w turze wywołanej zdarzeniem
  automatycznym (powiadomienie podagenta, wiadomość innej sesji) aplikacja pozwala tylko zaproponować kartę, a karta
  nie wskazuje innego folderu. Dlatego brief zaczyna się od „Przejdź do `<pełna ścieżka projektu>` (narzędzie
  zmiany katalogu albo ścieżki bezwzględne), zanim zaczniesz” i niesie cały potrzebny kontekst (dowody, pliki,
  co znaczy „gotowe”). Bez takiego narzędzia zapisz brief w sekcji 10 retro do skopiowania.
  Gdy pozycji jest więcej niż 8 (zwykle retro zero), łącz w jedno pytanie pozycje tego samego projektu, które
  trafiłyby do jednego zadania; sprawy bezpieczeństwa (rotacje, klucze, hasła) zawsze pytaj osobno.

Zapisz odpowiedzi w sekcji 9 retro, własne odpowiedzi użytkownika dosłownie.

## Krok 5. Wdrożenie

1. `zobowiazania.md`: nowe wpisy `Z-NNN` (format w nagłówku pliku), wiersz oceny w tabeli każdego rozliczonego,
   zmiany statusu.
2. Reguły:
   - **tryb konta:** ogólne (wszystkie projekty) → `~/.claude/CLAUDE.md`, krótko, z numerem `Z-NNN`; wiedza
     przekrojowa (pułapki komputera i narzędzi) → `nauki.md`; przy pierwszym wpisie zaproponuj jedną linię
     w `~/.claude/CLAUDE.md` odsyłającą do `nauki.md`, bo pamięć projektu ładuje się tylko w jego folderze;
   - **projektowe:** CLAUDE.md repo zgodnie z jego zasadami (jeśli zmiany idą przez PR: gałąź
     `retro/rNN-<temat>` w osobnym worktree i PR);
   - pamięć projektu (`~/.claude/projects/*/memory/`) → wpis `feedback` z odnośnikiem `Z-NNN`, bez powielania
     treści z `nauki.md`.
3. `metryki.csv`: `python "${CLAUDE_SKILL_DIR}/scripts/dopisz_metryki.py" --retro RNN --zobowiazania <aktywne>`
   (wiersz z najnowszego `metryki.json`; brakujące kolumny nowszej wersji pluginu dopisuje na końcu nagłówka).
4. W retro: sekcja 10 (co, gdzie, commit lub PR), `**Status:** zakończone` (to resetuje licznik przypomnienia).
5. Commit: tryb konta w katalogu roboczym; tryb projektu w repo (wg jego zasad), `retro(RNN): <najważniejsza zmiana>`.
   Commit obejmuje też `tokeny-tydzien.csv` (trend); archiwum `dane/tokeny-archiwum.json` zostaje poza gitem.

## Krok 6. Zamknięcie

W czacie 5–8 zdań: najważniejszy wniosek, co przyjęto, co się zmienia od jutra, odnośnik do pliku retro.

## Utrzymanie

Zainstalowana kopia pluginu jest nadpisywana przy aktualizacji: zmian skillu nie rób w niej, tylko w repo pluginu
(test: `python -m unittest discover -s testy` w repo). Zmianę, którą retro uzna za potrzebną, zapisz w sekcji 10
retro jako propozycję dla repo pluginu. Skrypty i treść z ukośnikami odwrotnymi pisz narzędziem Write, nie przez
heredoc basha.
