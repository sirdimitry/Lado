// Metadata-only diagnostics. Typed text must never be passed to this file.
#pragma once

#include <filesystem>
#include <string>

namespace lado {

std::filesystem::path log_path();

// Rotates at ~256 KiB. Safe to call from the UI and the secure-input worker.
void log_message(const wchar_t* format, ...);

}  // namespace lado
