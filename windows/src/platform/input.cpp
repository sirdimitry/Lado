#include "input.h"

#include <windows.h>

#include <vector>

namespace lado::input {
namespace {

bool send(const std::vector<INPUT>& inputs) {
  if (inputs.empty()) return true;
  const UINT sent = SendInput(static_cast<UINT>(inputs.size()),
                              const_cast<INPUT*>(inputs.data()), sizeof(INPUT));
  return sent == inputs.size();
}

void append_unicode(std::vector<INPUT>& inputs, wchar_t unit) {
  INPUT down = {};
  down.type = INPUT_KEYBOARD;
  down.ki.wVk = 0;
  down.ki.wScan = static_cast<WORD>(unit);
  down.ki.dwFlags = KEYEVENTF_UNICODE;
  down.ki.dwExtraInfo = static_cast<ULONG_PTR>(kInjectionTag);
  inputs.push_back(down);

  INPUT up = down;
  up.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP;
  inputs.push_back(up);
}

}  // namespace

bool replace_backward(int delete_units, std::wstring_view text) {
  if (delete_units < 0 || delete_units > kMaxDeleteUnits) return false;
  if (text.size() > kMaxTextUnits) return false;
  if (delete_units == 0 && text.empty()) return true;

  std::vector<INPUT> inputs;
  inputs.reserve(static_cast<size_t>(delete_units) * 2 + text.size() * 2);

  INPUT back = {};
  back.type = INPUT_KEYBOARD;
  back.ki.wVk = VK_BACK;
  back.ki.wScan = static_cast<WORD>(MapVirtualKeyW(VK_BACK, MAPVK_VK_TO_VSC));
  back.ki.dwExtraInfo = static_cast<ULONG_PTR>(kInjectionTag);
  for (int i = 0; i < delete_units; ++i) {
    inputs.push_back(back);
    back.ki.dwFlags = KEYEVENTF_KEYUP;
    inputs.push_back(back);
    back.ki.dwFlags = 0;
  }

  for (wchar_t unit : text) append_unicode(inputs, unit);
  return send(inputs);
}

bool type_text(std::wstring_view text) {
  if (text.size() > kMaxTextUnits) return false;
  std::vector<INPUT> inputs;
  inputs.reserve(text.size() * 2);
  for (wchar_t unit : text) append_unicode(inputs, unit);
  return send(inputs);
}

}  // namespace lado::input
