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
#include <mutex>
#include <thread>

namespace lado {

enum class SecureState { Unknown, Clear, Secure };

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
};

}  // namespace lado
