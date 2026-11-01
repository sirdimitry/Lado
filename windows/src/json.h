// A deliberately small JSON reader/writer. Settings are the only file format,
// so the parser is bounded (depth, size) and rejects anything it does not
// understand instead of guessing.
#pragma once

#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace lado::json {

class Value {
 public:
  enum class Type { Null, Bool, Number, String, Array, Object };

  using Array = std::vector<Value>;
  using Object = std::vector<std::pair<std::wstring, Value>>;

  Value() = default;
  explicit Value(bool value) : type_(Type::Bool), bool_(value) {}
  explicit Value(double value) : type_(Type::Number), number_(value) {}
  explicit Value(std::wstring value) : type_(Type::String), string_(std::move(value)) {}

  static Value make_array();
  static Value make_object();

  Type type() const { return type_; }
  bool is_null() const { return type_ == Type::Null; }
  bool is_bool() const { return type_ == Type::Bool; }
  bool is_number() const { return type_ == Type::Number; }
  bool is_string() const { return type_ == Type::String; }
  bool is_array() const { return type_ == Type::Array; }
  bool is_object() const { return type_ == Type::Object; }

  bool as_bool(bool fallback = false) const;
  double as_number(double fallback = 0.0) const;
  const std::wstring& as_string() const { return string_; }

  Array& items() { return array_; }
  const Array& items() const { return array_; }
  Object& members() { return object_; }
  const Object& members() const { return object_; }

  const Value* find(std::wstring_view key) const;
  void push(Value value);
  void set(std::wstring key, Value value);

 private:
  Type type_ = Type::Null;
  bool bool_ = false;
  double number_ = 0.0;
  std::wstring string_;
  Array array_;
  Object object_;
};

std::optional<Value> parse(std::wstring_view text, std::wstring* error);
std::wstring serialize(const Value& value, int indent = 2);

}  // namespace lado::json
