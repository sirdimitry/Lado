# rc.8 policy (source candidate)

Whole-field reads and writes remain disabled. WebKit uses the strict AX range operation with a bounded read-back. For the tested Codex contenteditable only, when the AX setter returns success but the bounded read-back proves the text did not change, Lado may send **one** bounded tagged synthetic batch: Backspaces for the exact observed word plus a Unicode replacement, at most 128 characters. Every event carries Lado's own marker, so its listen-only tap ignores it. Physical input is never suppressed, and there is no retry. Verification reads only the replaced span via `AXStringForRange`. No clipboard, typing history, network or telemetry.

В rc.8 запись целого поля по-прежнему отключена. WebKit использует строгий AX-диапазон с обязательной проверкой. Только для проверенного поля Codex, если AX сообщает успех, но проверка участка доказывает, что текст не изменился, Lado может отправить **одну** ограниченную помеченную синтетическую серию: Backspace на exact-наблюдавшееся слово и Unicode-замену, не более 128 символов. Каждое событие несёт метку Lado, поэтому собственный listen-only tap его игнорирует. Физический ввод не подавляется, повторов нет. Проверка читает только заменённый участок через `AXStringForRange`. Буфера обмена, истории ввода, сети и телеметрии нет.

Older candidate policies below are historical.

---

# Privacy / Приватность

## Русский

**Lado не отправляет набранный текст, не ведёт историю ввода и не сохраняет
набранный текст на диск.** Распознавание и преобразование работают без интернета.
Нет аналитики, аккаунта и загрузки моделей.

По запросу пользователя добавлена необязательная проверка обновлений GitHub:
при запуске и раз в час запрашивается только фиксированный публичный список релизов
`sirdimitry/Lado`. В запрос не включаются набранный текст, исключения, документы,
аккаунт или идентификатор устройства. GitHub получает обычные данные соединения,
например IP-адрес. Автопроверку можно отключить в настройках; ручная проверка в меню
выполняет запрос только по нажатию. Таймаут и ошибка сети не мешают набору.

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
  безопасную замену через Accessibility, исправление слова пропускается. Исключение —
  одна ограниченная Chromium-серия, описанная в начале этого файла.

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
браузеру. Это не отправка текста со стороны Lado. По кнопке «Обновить» аналогично
открывается проверенная ссылка на GitHub DMG для установленного процессора;
приложение не устанавливает новую версию скрытно.

«Не сохраняет» означает отсутствие записи в коде приложения. Python не гарантирует
криптографическое затирание строк RAM; системная подкачка и системные дампы находятся
за пределами управления Lado. Исключения пользователя — намеренно сохраняемые
данные, поэтому не добавляйте в них пароли.

## English

**Lado never transmits typed text, records a typing history, or deliberately
writes typed text to disk.** Text processing works offline, without telemetry,
an account or model downloads.

Optional update checks request only the fixed public GitHub release endpoint for
`sirdimitry/Lado`, at startup and hourly. Requests contain no typing, personal
exceptions, documents, account or device identifiers. GitHub sees ordinary connection
metadata such as an IP address. Disable automatic checks in Settings; a manual
check makes a request only when chosen. Network failure does not block typing.
Choosing Update opens a validated matching GitHub DMG in the default browser;
installation uses the usual drag to Applications, with no silent app replacement.

The bounded RAM context contains up to three completed words and one current word
(128 characters each), plus a single temporary reversible edit. It is cleared on
focus changes, clicks, navigation, shortcuts, pause, other layouts and after 30
idle seconds. An existing user selection is read only on explicit double Shift, capped at 65,536
UTF-16 code units. Only its last reversible operation is retained, for up to 30
seconds. Word replacement validates only the bounded span already observed; it
does not read the document. Unsupported Accessibility word replacement is skipped, apart from the
single bounded Chromium fallback described at the top. No clipboard access is used.

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

## Opt-in development checks

The isolated compatibility runner is disabled in normal operation. When explicitly
started with compatibility flags, it sends public synthetic examples only to the
exact project-owned test pad and writes PASS/FAIL case names plus non-text diagnostic
metadata to `build/compatibility-results.json` (mode `0600`). It never reads secure
field contents, never contacts GitHub, restores temporary settings and closes both
test apps. This report contains no typed text and is not a typing history.

## Security reports

For a security issue, contact [@sirdimitry](https://x.com/sirdimitry). Do not post
passwords, private typed examples or sensitive application screenshots in public
GitHub issues. Synthetic examples are sufficient to reproduce layout problems.

## Input safety revision (2026-10-29)

The revised adapter uses listen-only observation and never submits keyboard
events. Up to 16 native event copies are held briefly in RAM; Unicode is decoded
only after fresh protected-field and focus checks outside the callback. Pending
events expire after 250 ms or are discarded on overflow/focus changes. Failed
atomic replacements are skipped, including explicit selections. A zero-content
`instance.lock` file under the settings directory prevents duplicate processes.
These source changes still require isolated live validation.

Исправленный адаптер только наблюдает события и не отправляет нажатия. В RAM
кратковременно остаётся до 16 копий системных событий; символы читаются после
новой проверки защиты и фокуса вне callback. События старше 250 мс, при
переполнении или смене фокуса отбрасываются. При отказе атомарной замены
исправление пропускается, в том числе для выделений. Пустой файл `instance.lock`
рядом с настройками предотвращает запуск двух копий. Живая проверка ещё нужна.

## rc.3 privacy and focus invariants

Whole-field reads are OFF by default. Only an explicitly enabled option and manual
double Shift can read/rewrite up to 16384 UTF-16 units. Automatic correction never
uses this path. A known current range and unchanged value/range are required.
The optional mode can reset formatting and is not an atomic compare-and-swap
against changes inside the editor. No text is transmitted or intentionally saved.

В rc.3 чтение целого поля выключено по умолчанию и никогда не применяется
автоисправлением. Только отдельная опция и ручной двойной Shift допускают работу
с целым коротким полем (до 16384 единиц UTF-16). Проверяются защита, цель, диапазон
и неизменность значения. Режим может сбросить форматирование; абсолютной
атомарности при изменениях редактора API не гарантирует. Ввод не сохраняется.

The background probe scans bounded element references and metadata, not document
values. Start timestamps and focus generations reject stale results. Core
Foundation equality identifies the same field across wrappers. The stopped
worker remains owned until exit, preventing duplicate workers. User-requested
diagnostic reports contain only metadata and permission/error states.
