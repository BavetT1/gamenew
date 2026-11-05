# Квест-сериал для изучающих язык (iOS 26, SwiftUI)

Интерактивная детективная история с выборами; любое слово можно нажать — перевод, озвучка,
«в карточки». ТЗ и план — `docs/PLAN.md`. Формат контента — `docs/CONTENT_FORMAT.md`.

## Договорённости
- iPhone, iOS 26, SwiftUI. Без сервера и регистрации. Изучаемые языки en, es; уровни A2, B1;
  интерфейс и переводы ru, en, es.
- Ядро берём из Leo (репозиторий `BavetT1/TASKS`): пакет `Packages/LeoCore` (SM-2 `Scheduler`,
  упражнения, `Lemmatizer`, `BookLanguage`), перевод — `Leo/Translation/TranslationService.swift`
  (Apple Translation на устройстве), озвучка — `Leo/Translation/Speaker.swift`.
- Голоса — только встроенный синтез Apple (`AVSpeechSynthesizer`); у героя свой голос через
  локаль, пол и высоту в `season.json`. Аудиофайлов нет.
- Контент — файлы в `content/`, не код. Новый эпизод не требует правки Swift.
- Иллюстрации рисует Claude в SVG (навык `illustrator`), к каждому кадру хранится промпт для
  возможной перегенерации внешним генератором.
- Агенты конвейера — навыки Claude Code в `.claude/skills/`, работают в рамках подписки.
  Точка входа — `new-episode`: один запрос владельца → готовый эпизод. Владелец согласует
  только план сюжета.
- Коммиты без идентификатора модели.

## Проверка
- Контент: `python3 tools/validate.py content/seasons/<сезон>`.
- Тестовый пример формата: `tools/fixtures/mini`.
