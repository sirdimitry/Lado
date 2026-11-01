// Switch the focused application's input language after a correction.
//
// Windows exposes this through WM_INPUTLANGCHANGEREQUEST; posting it to the
// focused control and the top-level window covers both classic Win32 editors
// and Chromium/WinUI hosts. Only an already installed layout is selected.
#pragma once

#include <windows.h>

#include "layout.h"

namespace lado {

HKL switch_to_language(Lang language);

}  // namespace lado
