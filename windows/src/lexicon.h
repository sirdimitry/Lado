// Compact RU/EN frequency lexicon loaded from a checked-in binary.
//
// The binary is generated from src/lado/data/frequencies.json.gz by
// tools/build_lexicon.py; the source of truth for the numbers stays the
// Python data file shared with the macOS engine.
#pragma once

#include <cstddef>
#include <filesystem>
#include <string>
#include <string_view>
#include <unordered_map>

#include "layout.h"

namespace lado {

class Lexicon {
 public:
  bool load(const std::filesystem::path& path);
  bool load_from_memory(const void* data, size_t size);
  bool loaded() const { return loaded_; }

  // Raw frequency weight (already divided by 100 like the Python engine).
  double score(std::wstring_view word, Lang lang) const;
  size_t size(Lang lang) const;

 private:
  bool read_table(const unsigned char*& cursor, const unsigned char* end,
                  std::unordered_map<std::wstring, float>* table);

  std::unordered_map<std::wstring, float> en_;
  std::unordered_map<std::wstring, float> ru_;
  bool loaded_ = false;
};

}  // namespace lado
