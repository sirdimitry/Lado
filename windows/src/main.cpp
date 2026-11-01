#include <windows.h>
#include <objbase.h>

#include "app.h"
#include "platform/log.h"

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE, PWSTR, int show_command) {
  const HRESULT com = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);

  HANDLE instance_mutex =
      CreateMutexW(nullptr, TRUE, L"Local\\Lado.Windows.SingleInstance");
  if (instance_mutex != nullptr && GetLastError() == ERROR_ALREADY_EXISTS) {
    if (HWND existing = FindWindowW(lado::kAppWindowClass, nullptr)) {
      PostMessageW(existing, lado::kShowSettingsMessage, 0, 0);
    }
    CloseHandle(instance_mutex);
    if (SUCCEEDED(com)) CoUninitialize();
    return 0;
  }

  lado::App app(instance);
  const int result = app.run(show_command);

  if (instance_mutex != nullptr) CloseHandle(instance_mutex);
  if (SUCCEEDED(com)) CoUninitialize();
  return result;
}
