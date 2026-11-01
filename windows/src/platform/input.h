// Synthetic replacement through SendInput. Unicode injection is used instead
// of the clipboard: nothing is read, nothing is persisted.
#pragma once

#include <cstdint>
#include <string>
#include <string_view>

namespace lado::input {

// Every synthetic event carries this tag in dwExtraInfo. It lets the keyboard
// hook ignore Lado's own replacement even in the QA mode that accepts injected
// input from a test harness.
inline constexpr uintptr_t kInjectionTag = 0x4C41444F;  // "LADO"

constexpr int kMaxDeleteUnits = 1024;
constexpr size_t kMaxTextUnits = 4096;

// Deletes `delete_units` UTF-16 units before the caret and types `text` as one
// atomic SendInput batch. Returns false when the system rejected the batch
// (for example an elevated window protected by UIPI).
bool replace_backward(int delete_units, std::wstring_view text);

bool type_text(std::wstring_view text);

// Sends a bare Enter. Used when the original Enter was swallowed so the word
// could be converted before it reached the chat/search box.
bool press_enter();

}  // namespace lado::input
