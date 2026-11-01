#include "lexicon.h"

#include <cstdint>
#include <cstring>
#include <fstream>
#include <vector>

#include "util.h"

namespace lado {
namespace {

constexpr char kMagic[8] = {'L', 'A', 'D', 'O', 'L', 'E', 'X', '1'};
constexpr uint32_t kFormatVersion = 1;
constexpr size_t kMaxFileSize = 64u * 1024u * 1024u;
constexpr uint32_t kMaxEntries = 5u * 1000u * 1000u;

uint16_t read_u16(const unsigned char*& p, const unsigned char* end) {
  if (end - p < 2) return 0;
  uint16_t v = static_cast<uint16_t>(p[0] | (p[1] << 8));
  p += 2;
  return v;
}

uint32_t read_u32(const unsigned char*& p, const unsigned char* end) {
  if (end - p < 4) return 0;
  uint32_t v = static_cast<uint32_t>(p[0]) | (static_cast<uint32_t>(p[1]) << 8) |
               (static_cast<uint32_t>(p[2]) << 16) |
               (static_cast<uint32_t>(p[3]) << 24);
  p += 4;
  return v;
}

}  // namespace

bool Lexicon::load(const std::filesystem::path& path) {
  loaded_ = false;
  en_.clear();
  ru_.clear();

  std::ifstream file(path, std::ios::binary | std::ios::ate);
  if (!file) return false;
  const std::streamoff length = file.tellg();
  if (length <= 16 || static_cast<uint64_t>(length) > kMaxFileSize) return false;
  file.seekg(0);
  std::vector<unsigned char> data(static_cast<size_t>(length));
  if (!file.read(reinterpret_cast<char*>(data.data()), length)) return false;
  return load_from_memory(data.data(), data.size());
}

bool Lexicon::load_from_memory(const void* data, size_t size) {
  loaded_ = false;
  en_.clear();
  ru_.clear();
  if (data == nullptr || size <= 16 || size > kMaxFileSize) return false;

  const unsigned char* cursor = static_cast<const unsigned char*>(data);
  const unsigned char* end = cursor + size;
  if (std::memcmp(cursor, kMagic, sizeof(kMagic)) != 0) return false;
  cursor += sizeof(kMagic);
  if (read_u32(cursor, end) != kFormatVersion) return false;
  const uint16_t table_count = read_u16(cursor, end);
  if (table_count == 0 || table_count > 4) return false;

  for (uint16_t i = 0; i < table_count; ++i) {
    const uint16_t code_length = read_u16(cursor, end);
    if (code_length == 0 || code_length > 8 || end - cursor < code_length) {
      return false;
    }
    std::string code(reinterpret_cast<const char*>(cursor), code_length);
    cursor += code_length;
    std::unordered_map<std::wstring, float>* table = nullptr;
    if (code == "en") {
      table = &en_;
    } else if (code == "ru") {
      table = &ru_;
    } else {
      return false;
    }
    if (!read_table(cursor, end, table)) return false;
  }

  loaded_ = !en_.empty() && !ru_.empty();
  if (!loaded_) {
    en_.clear();
    ru_.clear();
  }
  return loaded_;
}

bool Lexicon::read_table(const unsigned char*& cursor, const unsigned char* end,
                         std::unordered_map<std::wstring, float>* table) {
  const uint32_t count = read_u32(cursor, end);
  if (count == 0 || count > kMaxEntries) return false;
  table->reserve(count);
  for (uint32_t i = 0; i < count; ++i) {
    const uint16_t units = read_u16(cursor, end);
    if (units == 0 || units > 255 || end - cursor < static_cast<ptrdiff_t>(units) * 2) {
      return false;
    }
    std::wstring word(units, L'\0');
    std::memcpy(word.data(), cursor, static_cast<size_t>(units) * 2);
    cursor += static_cast<size_t>(units) * 2;
    if (end - cursor < 4) return false;
    float score = 0.0f;
    std::memcpy(&score, cursor, sizeof(score));
    cursor += 4;
    (*table)[std::move(word)] = score;
  }
  return true;
}

double Lexicon::score(std::wstring_view word, Lang lang) const {
  const std::wstring key = casefold(word);
  if (lang == Lang::Ru) {
    auto found = ru_.find(key);
    return found == ru_.end() ? 0.0 : found->second;
  }
  if (lang == Lang::En) {
    auto found = en_.find(key);
    return found == en_.end() ? 0.0 : found->second;
  }
  return 0.0;
}

size_t Lexicon::size(Lang lang) const {
  return lang == Lang::Ru ? ru_.size() : lang == Lang::En ? en_.size() : 0;
}

}  // namespace lado
