#include "strings.h"

#include <windows.h>

namespace lado {
namespace {

constexpr UiStrings kRu{
    L"Lado — настройки",
    L"Раскладка",
    L"Слова-исключения",
    L"Приложения-исключения",
    L"Исправлять раскладку автоматически",
    L"Учитывать регистр исключений",
    L"Двойной Shift:",
    L"мс",
    L"Запускать при входе в Windows",
    L"По одному слову на строку. Исключения не мешают ручному двойному Shift.",
    L"Имя процесса, например chrome.exe. По одному на строку.",
    L"Lado обрабатывает текст только в памяти. Сохраняются лишь настройки и "
    L"явные исключения в %APPDATA%\\Lado. Пароли и защищённые поля отключают "
    L"обработку; сеть не используется.",
    L"Сохранить",
    L"Отмена",
    L"Раскладка: %s",
    L"русская (RU)",
    L"английская (EN)",
    L"другая",
    L"пауза",
    L"защищённый ввод",
    L"исключено",
    L"Lado · %s",
    L"Исправлять автоматически",
    L"Пауза",
    L"Не исправлять в этом приложении",
    L"Снова исправлять в этом приложении",
    L"Настройки…",
    L"О программе",
    L"Выход",
    L"О Lado",
    L"Lado %s — раскладка RU/EN для Windows.\n\n"
    L"Локальная обработка: без истории ввода, телеметрии и сети.\n"
    L"Двойной Shift: слово или выделение; в ручном режиме — вся фраза.\n\n"
    L"github.com/sirdimitry/Lado · MIT",
    L"Lado не смог перехватить клавиатуру. Перезапустите приложение; если ошибка "
    L"повторится, проверьте журнал %LOCALAPPDATA%\\Lado\\lado.log.",
    L"Словарь Lado не загрузился. Переустановите приложение.",
    L"Lado",
};

constexpr UiStrings kEn{
    L"Lado settings",
    L"Layout",
    L"Word exceptions",
    L"App exceptions",
    L"Correct the keyboard layout automatically",
    L"Case-sensitive exceptions",
    L"Double Shift:",
    L"ms",
    L"Start with Windows",
    L"One word per line. Exceptions do not block manual double Shift.",
    L"Process name, for example chrome.exe. One per line.",
    L"Lado processes text in memory only. Only settings and explicit exceptions "
    L"are saved in %APPDATA%\\Lado. Passwords and secure fields disable "
    L"processing; no network access is used.",
    L"Save",
    L"Cancel",
    L"Layout: %s",
    L"Russian (RU)",
    L"English (EN)",
    L"other",
    L"paused",
    L"secure input",
    L"excluded",
    L"Lado · %s",
    L"Correct automatically",
    L"Pause",
    L"Do not correct in this app",
    L"Correct in this app again",
    L"Settings…",
    L"About",
    L"Quit",
    L"About Lado",
    L"Lado %s — a RU/EN keyboard layout companion for Windows.\n\n"
    L"Local processing: no typing history, telemetry or network access.\n"
    L"Double Shift fixes a word or selection; in manual mode, the whole phrase.\n\n"
    L"github.com/sirdimitry/Lado · MIT",
    L"Lado could not install its keyboard hook. Restart the app; if the error "
    L"persists, check %LOCALAPPDATA%\\Lado\\lado.log.",
    L"Lado could not load its dictionary. Reinstall the app.",
    L"Lado",
};

}  // namespace

const UiStrings& ui_strings() {
  const LANGID language = GetUserDefaultUILanguage();
  return PRIMARYLANGID(language) == LANG_RUSSIAN ? kRu : kEn;
}

}  // namespace lado
