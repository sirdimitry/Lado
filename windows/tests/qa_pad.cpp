// Minimal Win32 text field used by tools/qa_typing.ps1 for an end-to-end
// check of the real keyboard hook and replacement path. Not part of the app.
//
//   LadoQaPad.exe             normal multi-line field
//   LadoQaPad.exe --password  single-line password field
#include <windows.h>

#include <cwchar>

namespace {

constexpr wchar_t kClass[] = L"LadoQaPadWindow";
HWND g_edit = nullptr;
bool g_password = false;

LRESULT CALLBACK WndProc(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam) {
  switch (message) {
    case WM_CREATE: {
      DWORD style = WS_CHILD | WS_VISIBLE | WS_VSCROLL | ES_AUTOVSCROLL;
      int height = 280;
      if (g_password) {
        style |= ES_PASSWORD | ES_AUTOHSCROLL;
        height = 28;
      } else {
        style |= ES_MULTILINE | ES_WANTRETURN;
      }
      g_edit = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", L"", style, 8, 8,
                               600, height, hwnd, reinterpret_cast<HMENU>(1),
                               GetModuleHandleW(nullptr), nullptr);
      SendMessageW(g_edit, WM_SETFONT,
                   reinterpret_cast<WPARAM>(GetStockObject(DEFAULT_GUI_FONT)),
                   TRUE);
      return 0;
    }
    case WM_SIZE:
      if (g_edit != nullptr) {
        const int edit_height = g_password ? 28 : HIWORD(lparam) - 16;
        MoveWindow(g_edit, 8, 8, LOWORD(lparam) - 16, edit_height, TRUE);
      }
      return 0;
    case WM_SETFOCUS:
      if (g_edit != nullptr) SetFocus(g_edit);
      return 0;
    case WM_CLOSE:
      DestroyWindow(hwnd);
      return 0;
    case WM_DESTROY:
      PostQuitMessage(0);
      return 0;
    default:
      break;
  }
  return DefWindowProcW(hwnd, message, wparam, lparam);
}

}  // namespace

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE, PWSTR command_line, int) {
  g_password = command_line != nullptr &&
               std::wcsstr(command_line, L"--password") != nullptr;

  WNDCLASSEXW window_class = {};
  window_class.cbSize = sizeof(window_class);
  window_class.lpfnWndProc = &WndProc;
  window_class.hInstance = instance;
  window_class.hCursor = LoadCursorW(nullptr, IDC_IBEAM);
  window_class.hbrBackground = reinterpret_cast<HBRUSH>(COLOR_WINDOW + 1);
  window_class.lpszClassName = kClass;
  if (!RegisterClassExW(&window_class)) return 1;

  HWND window = CreateWindowExW(0, kClass,
                                g_password ? L"Lado QA password pad"
                                           : L"Lado QA pad",
                                WS_OVERLAPPEDWINDOW, CW_USEDEFAULT,
                                CW_USEDEFAULT, 640, g_password ? 120 : 340,
                                nullptr, nullptr, instance, nullptr);
  if (window == nullptr) return 1;
  ShowWindow(window, SW_SHOWNORMAL);
  SetForegroundWindow(window);
  if (g_edit != nullptr) SetFocus(g_edit);

  MSG message = {};
  while (GetMessageW(&message, nullptr, 0, 0) > 0) {
    TranslateMessage(&message);
    DispatchMessageW(&message);
  }
  return 0;
}
