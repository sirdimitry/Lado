# Privacy / Приватность

## Русский

**Lado не отправляет набранный текст, не ведёт историю ввода и не сохраняет
набранный текст на диск.** Нет сетевого клиента, аналитики, аккаунта, автоматической
проверки обновлений и загрузки моделей. Приложение работает без интернета.

Чтобы преобразовать слово, программе необходим кратковременный контекст в памяти:

- До трёх завершённых слов с пробелами и текущего слова; каждое слово не длиннее
  128 символов. Переполнение отключает обработку данного токена.
- Контекст сбрасывается при смене поля/приложения/чужой раскладки, щелчке мышью,
  перемещении курсора, сочетании клавиш, паузе и после 30 секунд бездействия.
- Существующее пользовательское выделение читается только по явному двойному Shift и ограничено 65 536
  единицами UTF-16. Последняя операция может оставаться в RAM до 30 секунд для
  точного возврата. Это не постоянная история и не журнал.
- При замене слова дополнительно сверяется только короткий диапазон уже
  наблюдавшегося слова. Весь документ не считывается. Если редактор не поддерживает
  безопасную замену через Accessibility, исправление слова пропускается; серии
  удаляющих Backspace не используются.

На диске: `~/Library/Application Support/Lado/settings.json` — только настройки,
явно добавленные исключения слов и bundle ID приложений. Файл создаётся с правами
`0600`. При включённом пользователем автозапуске создаётся
`~/Library/LaunchAgents/com.sirdimitry.lado.plist`, содержащий путь к приложению.
В автозапуск не записывается текст. Удаление этих файлов сбрасывает настройки.

### Пароли и разрешения

Программа проверяет системный Secure Event Input, защищённый тип поля
`AXSecureTextField` и признак защищённого содержимого **до получения символов
клавиатурного события**. При обнаружении защиты обработка отключается, контекст
сбрасывается и значок становится приглушённым с замком. После выхода из поля
контекст начинается заново. Неизвестные и неподдерживаемые элементы блокируются.

Это не обещание распознать поле, которое стороннее приложение ошибочно представляет
как обычное текстовое. Нестандартные поля, браузеры и удалённые рабочие столы требуют
отдельной проверки. Менеджеры паролей и приложения для кода можно исключать целиком;
несколько распространённых приложений исключены по умолчанию.

Для наблюдения и изменения клавиатурных событий нужны системные разрешения macOS.
Они дают техническую возможность видеть ввод; ограничение его обработки обеспечено
кодом Lado и доступно для проверки в исходниках. Права root не используются.

### Границы обещания

Lado не использует буфер обмена и не пишет ввод в журналы или отчёты об ошибках.
Открытие авторских ссылок происходит только по нажатию и передаёт URL системному
браузеру. Это не отправка текста со стороны Lado.

«Не сохраняет» означает отсутствие записи в коде приложения. Python не гарантирует
криптографическое затирание строк RAM; системная подкачка и системные дампы находятся
за пределами управления Lado. Исключения пользователя — намеренно сохраняемые
данные, поэтому не добавляйте в них пароли.

## English

**Lado never transmits typed text, records a typing history, or deliberately
writes typed text to disk.** There is no network client, telemetry, account,
automatic update check, or model download. Normal operation is entirely offline.

The bounded RAM context contains up to three completed words and one current word
(128 characters each), plus a single temporary reversible edit. It is cleared on
focus changes, clicks, navigation, shortcuts, pause, other layouts and after 30
idle seconds. An existing user selection is read only on explicit double Shift, capped at 65,536
UTF-16 code units. Only its last reversible operation is retained, for up to 30
seconds. Word replacement validates only the bounded span already observed; it
does not read the document. Unsupported Accessibility word replacement is skipped,
without destructive Backspace bursts. No clipboard access is used.

Only preferences and explicit word/app exceptions are persisted in
`~/Library/Application Support/Lado/settings.json` (mode `0600`). Optional start at
login writes the application path to
`~/Library/LaunchAgents/com.sirdimitry.lado.plist`. Neither file stores typing.

Secure Event Input and protected accessibility fields are checked before event
characters are read. Detection disables processing, clears context and displays
a dim lock icon. Unknown/unsupported fields are blocked. An application that
mislabels a custom password field as ordinary text cannot be universally detected;
app exclusions provide an additional boundary. Browser/editor compatibility must
be tested, not assumed.

Accessibility permissions inherently allow observing input. Lado's limited use
of that access is enforced by reviewable code. Root access is not used. Author
links open in the default browser only when clicked; no typed text is passed.
Python cannot guarantee secure RAM erasure; OS swap/crash dumps are outside the
application's control. Explicit exceptions are intentionally saved, so never add
passwords to that list.

## Security reports

For a security issue, contact [@sirdimitry](https://x.com/sirdimitry). Do not post
passwords, private typed examples or sensitive application screenshots in public
GitHub issues. Synthetic examples are sufficient to reproduce layout problems.
