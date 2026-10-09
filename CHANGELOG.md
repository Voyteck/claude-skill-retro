# Zmiany

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
