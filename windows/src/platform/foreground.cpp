#include "foreground.h"

namespace lado {

void force_foreground(HWND window) {
  if (window == nullptr) return;
  const HWND current = GetForegroundWindow();
  if (current == window) {
    SetFocus(window);
    return;
  }

  const DWORD current_thread =
      current != nullptr ? GetWindowThreadProcessId(current, nullptr) : 0;
  const DWORD target_thread = GetWindowThreadProcessId(window, nullptr);
  bool attached = false;
  if (current_thread != 0 && target_thread != 0 &&
      current_thread != target_thread) {
    attached = AttachThreadInput(current_thread, target_thread, TRUE) != FALSE;
  }

  SetForegroundWindow(window);
  BringWindowToTop(window);
  SetFocus(window);

  if (attached) AttachThreadInput(current_thread, target_thread, FALSE);

  if (GetForegroundWindow() != window) {
    SetWindowPos(window, HWND_TOPMOST, 0, 0, 0, 0,
                 SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW);
    SetWindowPos(window, HWND_NOTOPMOST, 0, 0, 0, 0,
                 SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW);
    SetForegroundWindow(window);
  }
}

}  // namespace lado
