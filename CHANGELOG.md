# Zmiany

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
