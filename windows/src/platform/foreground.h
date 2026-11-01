// Bringing a window to the foreground from a tray callback.
//
// Clicking the notification area gives the foreground to Explorer, so a plain
// SetForegroundWindow from our process can be denied. Attaching to the current
// foreground thread is the documented user-input-free workaround; a brief
// topmost toggle is the fallback.
#pragma once

#include <windows.h>

namespace lado {

void force_foreground(HWND window);

}  // namespace lado
