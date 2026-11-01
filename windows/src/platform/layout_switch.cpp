#include "layout_switch.h"

#include <windows.h>

#include <vector>

namespace lado {
namespace {

HKL find_installed(WORD primary_language) {
  const int count = GetKeyboardLayoutList(0, nullptr);
  if (count <= 0) return nullptr;
  std::vector<HKL> layouts(static_cast<size_t>(count));
  if (GetKeyboardLayoutList(count, layouts.data()) <= 0) return nullptr;
  for (HKL layout : layouts) {
    const WORD id = LOWORD(reinterpret_cast<DWORD_PTR>(layout));
    if (PRIMARYLANGID(id) == primary_language) return layout;
  }
  return nullptr;
}

}  // namespace

HKL switch_to_language(Lang language) {
  if (language == Lang::None) return nullptr;
  const HWND foreground = GetForegroundWindow();
  if (foreground == nullptr) return nullptr;

  const WORD primary =
      language == Lang::Ru ? LANG_RUSSIAN : LANG_ENGLISH;
  const HKL target = find_installed(primary);
  if (target == nullptr) return nullptr;

  const DWORD thread = GetWindowThreadProcessId(foreground, nullptr);
  if (thread != 0 && GetKeyboardLayout(thread) == target) return nullptr;

  HWND focus = foreground;
  GUITHREADINFO info = {};
  info.cbSize = sizeof(info);
  if (thread != 0 && GetGUIThreadInfo(thread, &info) && info.hwndFocus != nullptr) {
    focus = info.hwndFocus;
  }

  PostMessageW(focus, WM_INPUTLANGCHANGEREQUEST, 0,
               reinterpret_cast<LPARAM>(target));
  if (focus != foreground) {
    PostMessageW(foreground, WM_INPUTLANGCHANGEREQUEST, 0,
                 reinterpret_cast<LPARAM>(target));
  }
  return target;
}

}  // namespace lado
