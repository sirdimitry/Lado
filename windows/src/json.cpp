#include "json.h"

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cwchar>

namespace lado::json {
namespace {

constexpr int kMaxDepth = 32;

class Parser {
 public:
  Parser(std::wstring_view text, std::wstring* error)
      : cursor_(text.data()), end_(text.data() + text.size()), error_(error) {}

  std::optional<Value> run() {
    skip_space();
    auto value = parse_value(0);
    if (!value) return std::nullopt;
    skip_space();
    if (cursor_ != end_) {
      fail(L"trailing characters");
      return std::nullopt;
    }
    return value;
  }

 private:
  void fail(const wchar_t* message) {
    if (error_ != nullptr && error_->empty()) *error_ = message;
  }

  void skip_space() {
    while (cursor_ != end_ &&
           (*cursor_ == L' ' || *cursor_ == L'\t' || *cursor_ == L'\r' ||
            *cursor_ == L'\n')) {
      ++cursor_;
    }
  }

  bool consume(wchar_t expected) {
    if (cursor_ != end_ && *cursor_ == expected) {
      ++cursor_;
      return true;
    }
    return false;
  }

  std::optional<Value> parse_value(int depth) {
    if (depth > kMaxDepth) {
      fail(L"nesting is too deep");
      return std::nullopt;
    }
    if (cursor_ == end_) {
      fail(L"unexpected end of input");
      return std::nullopt;
    }
    switch (*cursor_) {
      case L'{':
        return parse_object(depth);
      case L'[':
        return parse_array(depth);
      case L'"':
        return parse_string_value();
      case L't':
        return parse_literal(L"true", Value(true));
      case L'f':
        return parse_literal(L"false", Value(false));
      case L'n':
        return parse_literal(L"null", Value());
      default:
        return parse_number();
    }
  }

  std::optional<Value> parse_literal(std::wstring_view literal, Value value) {
    if (static_cast<size_t>(end_ - cursor_) < literal.size() ||
        std::wstring_view(cursor_, literal.size()) != literal) {
      fail(L"invalid literal");
      return std::nullopt;
    }
    cursor_ += literal.size();
    return value;
  }

  std::optional<Value> parse_object(int depth) {
    consume(L'{');
    Value object = Value::make_object();
    skip_space();
    if (consume(L'}')) return object;
    while (true) {
      skip_space();
      if (cursor_ == end_ || *cursor_ != L'"') {
        fail(L"object keys must be strings");
        return std::nullopt;
      }
      auto key = parse_string();
      if (!key) return std::nullopt;
      skip_space();
      if (!consume(L':')) {
        fail(L"expected ':' after object key");
        return std::nullopt;
      }
      skip_space();
      auto value = parse_value(depth + 1);
      if (!value) return std::nullopt;
      object.set(std::move(*key), std::move(*value));
      skip_space();
      if (consume(L'}')) return object;
      if (!consume(L',')) {
        fail(L"expected ',' or '}' in object");
        return std::nullopt;
      }
    }
  }

  std::optional<Value> parse_array(int depth) {
    consume(L'[');
    Value array = Value::make_array();
    skip_space();
    if (consume(L']')) return array;
    while (true) {
      skip_space();
      auto value = parse_value(depth + 1);
      if (!value) return std::nullopt;
      array.push(std::move(*value));
      skip_space();
      if (consume(L']')) return array;
      if (!consume(L',')) {
        fail(L"expected ',' or ']' in array");
        return std::nullopt;
      }
    }
  }

  std::optional<Value> parse_string_value() {
    auto text = parse_string();
    if (!text) return std::nullopt;
    return Value(std::move(*text));
  }

  std::optional<std::wstring> parse_string() {
    if (!consume(L'"')) {
      fail(L"expected string");
      return std::nullopt;
    }
    std::wstring out;
    while (cursor_ != end_) {
      const wchar_t c = *cursor_++;
      if (c == L'"') return out;
      if (c == L'\\') {
        if (cursor_ == end_) break;
        const wchar_t escape = *cursor_++;
        switch (escape) {
          case L'"': out.push_back(L'"'); break;
          case L'\\': out.push_back(L'\\'); break;
          case L'/': out.push_back(L'/'); break;
          case L'b': out.push_back(L'\b'); break;
          case L'f': out.push_back(L'\f'); break;
          case L'n': out.push_back(L'\n'); break;
          case L'r': out.push_back(L'\r'); break;
          case L't': out.push_back(L'\t'); break;
          case L'u': {
            uint32_t unit = 0;
            if (!read_hex4(&unit)) {
              fail(L"invalid \\u escape");
              return std::nullopt;
            }
            if (unit >= 0xD800 && unit <= 0xDBFF) {
              // High surrogate: require the low half to keep text well-formed.
              if (end_ - cursor_ < 2 || cursor_[0] != L'\\' || cursor_[1] != L'u') {
                fail(L"lone high surrogate");
                return std::nullopt;
              }
              cursor_ += 2;
              uint32_t low = 0;
              if (!read_hex4(&low) || low < 0xDC00 || low > 0xDFFF) {
                fail(L"invalid surrogate pair");
                return std::nullopt;
              }
              unit = 0x10000 + ((unit - 0xD800) << 10) + (low - 0xDC00);
              out.push_back(static_cast<wchar_t>(0xD800 + ((unit - 0x10000) >> 10)));
              out.push_back(static_cast<wchar_t>(0xDC00 + ((unit - 0x10000) & 0x3FF)));
            } else if (unit >= 0xDC00 && unit <= 0xDFFF) {
              fail(L"lone low surrogate");
              return std::nullopt;
            } else {
              out.push_back(static_cast<wchar_t>(unit));
            }
            break;
          }
          default:
            fail(L"unknown escape sequence");
            return std::nullopt;
        }
      } else if (c < 0x20) {
        fail(L"raw control character in string");
        return std::nullopt;
      } else {
        out.push_back(c);
      }
    }
    fail(L"unterminated string");
    return std::nullopt;
  }

  bool read_hex4(uint32_t* value) {
    uint32_t result = 0;
    for (int i = 0; i < 4; ++i) {
      if (cursor_ == end_) return false;
      const wchar_t c = *cursor_++;
      int digit = -1;
      if (c >= L'0' && c <= L'9') {
        digit = c - L'0';
      } else if (c >= L'a' && c <= L'f') {
        digit = c - L'a' + 10;
      } else if (c >= L'A' && c <= L'F') {
        digit = c - L'A' + 10;
      } else {
        return false;
      }
      result = result * 16 + static_cast<uint32_t>(digit);
    }
    *value = result;
    return true;
  }

  std::optional<Value> parse_number() {
    const wchar_t* start = cursor_;
    if (cursor_ != end_ && *cursor_ == L'-') ++cursor_;
    bool digits = false;
    while (cursor_ != end_ && *cursor_ >= L'0' && *cursor_ <= L'9') {
      ++cursor_;
      digits = true;
    }
    if (!digits) {
      fail(L"expected a value");
      return std::nullopt;
    }
    if (cursor_ != end_ && *cursor_ == L'.') {
      ++cursor_;
      while (cursor_ != end_ && *cursor_ >= L'0' && *cursor_ <= L'9') ++cursor_;
    }
    if (cursor_ != end_ && (*cursor_ == L'e' || *cursor_ == L'E')) {
      ++cursor_;
      if (cursor_ != end_ && (*cursor_ == L'+' || *cursor_ == L'-')) ++cursor_;
      bool exponent_digits = false;
      while (cursor_ != end_ && *cursor_ >= L'0' && *cursor_ <= L'9') {
        ++cursor_;
        exponent_digits = true;
      }
      if (!exponent_digits) {
        fail(L"invalid exponent");
        return std::nullopt;
      }
    }
    std::wstring text(start, cursor_);
    wchar_t* parsed_end = nullptr;
    const double value = std::wcstod(text.c_str(), &parsed_end);
    if (parsed_end == text.c_str() || !std::isfinite(value)) {
      fail(L"invalid number");
      return std::nullopt;
    }
    return Value(value);
  }

  const wchar_t* cursor_;
  const wchar_t* end_;
  std::wstring* error_;
};

void append_escaped(std::wstring& out, std::wstring_view text) {
  for (wchar_t c : text) {
    switch (c) {
      case L'"': out += L"\\\""; break;
      case L'\\': out += L"\\\\"; break;
      case L'\n': out += L"\\n"; break;
      case L'\r': out += L"\\r"; break;
      case L'\t': out += L"\\t"; break;
      case L'\b': out += L"\\b"; break;
      case L'\f': out += L"\\f"; break;
      default:
        if (c < 0x20) {
          wchar_t buffer[7];
          _snwprintf(buffer, 7, L"\\u%04x", static_cast<unsigned>(c));
          out += buffer;
        } else {
          out.push_back(c);
        }
    }
  }
}

void write_value(std::wstring& out, const Value& value, int depth, int indent);

void write_indent(std::wstring& out, int count) {
  out.append(static_cast<size_t>(count), L' ');
}

void write_value(std::wstring& out, const Value& value, int depth, int indent) {
  switch (value.type()) {
    case Value::Type::Null: out += L"null"; break;
    case Value::Type::Bool: out += value.as_bool() ? L"true" : L"false"; break;
    case Value::Type::Number: {
      const double number = value.as_number();
      if (std::floor(number) == number && std::fabs(number) < 1e15) {
        wchar_t buffer[32];
        _snwprintf(buffer, 32, L"%.0f",
                      number == 0.0 ? 0.0 : number);  // avoid "-0"
        out += buffer;
      } else {
        wchar_t buffer[40];
        _snwprintf(buffer, 40, L"%.17g", number);
        out += buffer;
      }
      break;
    }
    case Value::Type::String:
      out.push_back(L'"');
      append_escaped(out, value.as_string());
      out.push_back(L'"');
      break;
    case Value::Type::Array: {
      if (value.items().empty()) {
        out += L"[]";
        break;
      }
      out += L"[\n";
      for (size_t i = 0; i < value.items().size(); ++i) {
        write_indent(out, (depth + 1) * indent);
        write_value(out, value.items()[i], depth + 1, indent);
        if (i + 1 < value.items().size()) out.push_back(L',');
        out.push_back(L'\n');
      }
      write_indent(out, depth * indent);
      out.push_back(L']');
      break;
    }
    case Value::Type::Object: {
      if (value.members().empty()) {
        out += L"{}";
        break;
      }
      out += L"{\n";
      for (size_t i = 0; i < value.members().size(); ++i) {
        write_indent(out, (depth + 1) * indent);
        out.push_back(L'"');
        append_escaped(out, value.members()[i].first);
        out += L"\": ";
        write_value(out, value.members()[i].second, depth + 1, indent);
        if (i + 1 < value.members().size()) out.push_back(L',');
        out.push_back(L'\n');
      }
      write_indent(out, depth * indent);
      out.push_back(L'}');
      break;
    }
  }
}

}  // namespace

Value Value::make_array() {
  Value value;
  value.type_ = Type::Array;
  return value;
}

Value Value::make_object() {
  Value value;
  value.type_ = Type::Object;
  return value;
}

bool Value::as_bool(bool fallback) const {
  return type_ == Type::Bool ? bool_ : fallback;
}

double Value::as_number(double fallback) const {
  return type_ == Type::Number ? number_ : fallback;
}

const Value* Value::find(std::wstring_view key) const {
  for (const auto& member : object_) {
    if (member.first == key) return &member.second;
  }
  return nullptr;
}

void Value::push(Value value) { array_.push_back(std::move(value)); }

void Value::set(std::wstring key, Value value) {
  for (auto& member : object_) {
    if (member.first == key) {
      member.second = std::move(value);
      return;
    }
  }
  object_.emplace_back(std::move(key), std::move(value));
}

std::optional<Value> parse(std::wstring_view text, std::wstring* error) {
  if (error != nullptr) error->clear();
  Parser parser(text, error);
  return parser.run();
}

std::wstring serialize(const Value& value, int indent) {
  std::wstring out;
  write_value(out, value, 0, indent);
  out.push_back(L'\n');
  return out;
}

}  // namespace lado::json
