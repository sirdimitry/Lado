// Minimal Win32 text field used by tools/qa_typing.ps1 for an end-to-end
// check of the real keyboard hook and replacement path. Not part of the app.
//
//   LadoQaPad.exe [--password] [--prefill <text>] [--select-all]
//                 [--report <path>]
//
// The report path receives the control's text (UTF-8) when the harness posts
// WM_APP+1. Reading it in-process avoids cross-process WM_GETTEXT limits on
// password fields.
#include <windows.h>
#include <richedit.h>

#include <cstdint>
#include <cwchar>
#include <string>

namespace {

constexpr wchar_t kClass[] = L"LadoQaPadWindow";
constexpr UINT kDumpMessage = WM_APP + 1;

HWND g_edit = nullptr;
bool g_password = false;
bool g_select_all = false;
bool g_richedit = false;
std::wstring g_prefill;
std::wstring g_report_path;

void dump_report() {
  if (g_report_path.empty() || g_edit == nullptr) return;
  const int length = GetWindowTextLengthW(g_edit);
  std::wstring text(static_cast<size_t>(length) + 1, L'\0');
  const int copied = GetWindowTextW(g_edit, text.data(), length + 1);
  text.resize(copied > 0 ? static_cast<size_t>(copied) : 0);

  const int bytes = WideCharToMultiByte(CP_UTF8, 0, text.data(),
                                        static_cast<int>(text.size()), nullptr,
                                        0, nullptr, nullptr);
  std::string utf8(static_cast<size_t>(bytes > 0 ? bytes : 0), '\0');
  if (bytes > 0) {
    WideCharToMultiByte(CP_UTF8, 0, text.data(),
                        static_cast<int>(text.size()), utf8.data(), bytes,
                        nullptr, nullptr);
  }

  HANDLE file = CreateFileW(g_report_path.c_str(), GENERIC_WRITE, 0, nullptr,
                            CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
  if (file == INVALID_HANDLE_VALUE) return;
  DWORD written = 0;
  WriteFile(file, utf8.data(), static_cast<DWORD>(utf8.size()), &written,
            nullptr);
  CloseHandle(file);
}

std::wstring option_value(const std::wstring& command, const wchar_t* marker) {
  const size_t position = command.find(marker);
  if (position == std::wstring::npos) return {};
  size_t start = position + std::wcslen(marker);
  while (start < command.size() && command[start] == L' ') ++start;
  size_t end = start;
  if (start < command.size() && command[start] == L'"') {
    ++start;
    end = command.find(L'"', start);
  } else {
    end = command.find(L' ', start);
  }
  if (end == std::wstring::npos) end = command.size();
  return command.substr(start, end - start);
}

void parse_command_line(PWSTR command_line) {
  const std::wstring command = command_line != nullptr ? command_line : L"";
  g_password = command.find(L"--password") != std::wstring::npos;
  g_select_all = command.find(L"--select-all") != std::wstring::npos;
  g_richedit = command.find(L"--richedit") != std::wstring::npos;
  g_prefill = option_value(command, L"--prefill");
  g_report_path = option_value(command, L"--report");
}

const wchar_t* edit_class() {
  if (!g_richedit) return L"EDIT";
  static HMODULE rich_edit = LoadLibraryW(L"Msftedit.dll");
  return rich_edit != nullptr ? MSFTEDIT_CLASS : L"EDIT";
}

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
      g_edit = CreateWindowExW(WS_EX_CLIENTEDGE, edit_class(), L"", style, 8, 8,
                               600, height, hwnd, reinterpret_cast<HMENU>(1),
                               GetModuleHandleW(nullptr), nullptr);
      SendMessageW(g_edit, WM_SETFONT,
                   reinterpret_cast<WPARAM>(GetStockObject(DEFAULT_GUI_FONT)),
                   TRUE);
      if (!g_prefill.empty()) SetWindowTextW(g_edit, g_prefill.c_str());
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
    case kDumpMessage:
      dump_report();
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
  parse_command_line(command_line);

  WNDCLASSEXW window_class = {};
  window_class.cbSize = sizeof(window_class);
  window_class.lpfnWndProc = &WndProc;
  window_class.hInstance = instance;
  window_class.hCursor = LoadCursorW(nullptr, IDC_IBEAM);
  window_class.hbrBackground = reinterpret_cast<HBRUSH>(COLOR_WINDOW + 1);
  window_class.lpszClassName = kClass;
  if (!RegisterClassExW(&window_class)) return 1;

  HWND window = CreateWindowExW(
      0, kClass,
      g_password ? L"Lado QA password pad" : L"Lado QA pad",
      WS_OVERLAPPEDWINDOW, CW_USEDEFAULT, CW_USEDEFAULT, 640,
      g_password ? 120 : 340, nullptr, nullptr, instance, nullptr);
  if (window == nullptr) return 1;
  ShowWindow(window, SW_SHOWNORMAL);
  SetForegroundWindow(window);
  if (g_edit != nullptr) {
    SetFocus(g_edit);
    if (g_select_all) SendMessageW(g_edit, EM_SETSEL, 0, -1);
  }

  MSG message = {};
  while (GetMessageW(&message, nullptr, 0, 0) > 0) {
    TranslateMessage(&message);
    DispatchMessageW(&message);
  }
  return 0;
}
