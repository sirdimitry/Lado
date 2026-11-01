// "Start with Windows" is a per-user Run key entry; no service, no elevation.
#pragma once

#include <string>

namespace lado {

bool autostart_enabled();
bool set_autostart(bool enabled);
std::wstring current_executable_path();

}  // namespace lado
