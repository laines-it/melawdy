# Шрифты страницы статьи

Локальные WOFF2-файлы используются только в `css/article.css`; обращения к CDN во время просмотра страницы отсутствуют.

- Cormorant Garamond: начертания 400 и 700, [Google Fonts](https://fonts.google.com/specimen/Cormorant+Garamond).
- Inter: начертания 400, 500 и 700, [Google Fonts](https://fonts.google.com/specimen/Inter).

Источники: Google Fonts CSS API и `fonts.gstatic.com`. Файлы преобразованы из TTF в WOFF2 с помощью fontTools/Brotli, сохранены латиница, кириллица, пунктуация и знаки валют (`U+0000–024F`, `U+0400–052F`, `U+2000–206F`, `U+20A0–20CF`). Общий размер пяти шрифтов — около 208 КиБ. Инструменты преобразования не являются зависимостями приложения.

Лицензии SIL Open Font License 1.1 сохранены рядом: `cormorantgaramond-OFL.txt`, `inter-OFL.txt`.
