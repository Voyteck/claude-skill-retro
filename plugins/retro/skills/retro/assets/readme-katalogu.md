# Retro: katalog roboczy

Stan retrospektyw sposobu pracy z Claude Code. Mechanizm (procedura, skrypty, szablony) to plugin `retro`;
tutaj są tylko wyniki i stan między retro. Retro uruchamia `/retro:retro` albo prośba „zróbmy retro”.

| plik | rola |
|---|---|
| `konfiguracja.json` | tryb, kalendarz, próg przypomnienia, poprawki nazw projektów (opis pól w pluginie: `references/konfiguracja.md`) |
| `zobowiazania.md` | rejestr zobowiązań: kręgosłup ciągłości między retro |
| `retro/RNN-RRRR-MM-DD.md` | kolejne retro; `**Status:** zakończone` resetuje licznik przypomnienia |
| `metryki.csv` | metryki trendu, wiersz na retro |
| `nauki.md` | (tryb konta) wiedza dotycząca więcej niż jednego projektu |
| `dane/` | wyciągi z transkrypcji, **poza gitem** (treść sesji) |
