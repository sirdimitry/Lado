// Password/secure-field detection through UI Automation.
//
// The check runs on a worker thread because a cross-process UIA call can block
// when the focused application is unresponsive. The UI thread only reads an
// atomic state; while a check is overdue the state is reported as Unknown and
// all corrections are suppressed.
#pragma once

#include <windows.h>

#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <mutex>
#include <string>
#include <thread>

namespace lado {

enum class SecureState { Unknown, Clear, Secure };

enum class SelectionStatus {
  Empty,    // no selection, no text pattern, or nothing readable
  Text,     // a usable single-line selection
  Refused,  // a selection exists but is multiline/long/multi-range
};

struct SelectionResult {
  SelectionStatus status = SelectionStatus::Empty;
  std::wstring text;
};

class SecureWatcher {
 public:
  void start();

  // Returns true when the worker thread joined. When it returns false the
  // worker is detached inside a blocking UIA call; the owner must not destroy
  // this object afterwards (App leaks it intentionally at exit).
  bool stop();

  SecureState state() const { return state_.load(std::memory_order_relaxed); }

  SecureState effective_state() const;

  void refresh_soon();

  // Asks the worker to read the focused element's selection through UI
  // Automation. The result is collected later with take_selection(), so the
  // UI thread and the low-level hook never block on a cross-process call.
  void request_selection();
  bool take_selection(SelectionResult* result);

 private:
  void worker();

  std::thread thread_;
  std::mutex mutex_;
  std::condition_variable cv_;
  bool stop_ = false;
  bool refresh_ = false;
  bool started_ = false;
  std::atomic<SecureState> state_{SecureState::Unknown};
  std::atomic<ULONGLONG> busy_since_{0};

  bool selection_requested_ = false;
  bool selection_consumed_ = true;
  uint64_t selection_request_id_ = 0;
  uint64_t selection_done_id_ = 0;
  SelectionResult selection_result_;
};

}  // namespace lado
