cmake_minimum_required(VERSION 3.21)

project(LadoWindows VERSION 0.1.0 LANGUAGES CXX RC)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/W4 /permissive- /utf-8 /EHsc)
  add_compile_definitions(_CRT_SECURE_NO_WARNINGS)
else()
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

set(LADO_VERSION_STRING "0.1.0-windows.1")

add_library(lado_core STATIC
  src/engine.cpp
  src/json.cpp
  src/layout.cpp
  src/lexicon.cpp
  src/settings.cpp
  src/util.cpp
)
target_include_directories(lado_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_compile_definitions(lado_core PUBLIC
  UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX
  WINVER=0x0A00 _WIN32_WINNT=0x0A00
)

set(ICON_DIR "${CMAKE_CURRENT_SOURCE_DIR}/assets/icons")
set(SRC_DIR "${CMAKE_CURRENT_SOURCE_DIR}/src")
set(LEXICON "${CMAKE_CURRENT_SOURCE_DIR}/data/lexicon.bin")
set(MANIFEST "${CMAKE_CURRENT_SOURCE_DIR}/src/lado.manifest")
configure_file(src/resources.rc.in ${CMAKE_CURRENT_BINARY_DIR}/resources.rc @ONLY)

add_executable(Lado WIN32
  src/main.cpp
  src/app.cpp
  src/strings.cpp
  src/platform/autostart.cpp
  src/platform/focus.cpp
  src/platform/foreground.cpp
  src/platform/hook.cpp
  src/platform/input.cpp
  src/platform/log.cpp
  src/platform/secure.cpp
  src/platform/tray.cpp
  src/platform/ui.cpp
  ${CMAKE_CURRENT_BINARY_DIR}/resources.rc
)
target_link_libraries(Lado PRIVATE
  lado_core
  user32 gdi32 shell32 advapi32 ole32 oleaut32 uiautomationcore
)
target_compile_definitions(Lado PRIVATE LADO_VERSION_STRING="${LADO_VERSION_STRING}")

if(MINGW)
  target_link_options(Lado PRIVATE -municode -static -static-libgcc -static-libstdc++)
endif()

if(MSVC)
  # resources.rc already embeds ID 1 / type 24; the linker would add a second
  # auto-generated manifest and CVTRES rejects the duplicate.
  target_link_options(Lado PRIVATE /MANIFEST:NO)
endif()

add_executable(lado_tests tests/test_main.cpp)
target_link_libraries(lado_tests PRIVATE lado_core)
target_compile_definitions(lado_tests PRIVATE
  LADO_LEXICON_PATH="${CMAKE_CURRENT_SOURCE_DIR}/data/lexicon.bin"
  LADO_CORPUS_PATH="${CMAKE_CURRENT_SOURCE_DIR}/../tests/corpus.json"
)

# Manual end-to-end QA target, driven by tools/qa_typing.ps1. Not installed.
add_executable(LadoQaPad WIN32 tests/qa_pad.cpp)
target_link_libraries(LadoQaPad PRIVATE user32 gdi32)
target_compile_definitions(LadoQaPad PRIVATE
  UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX
  WINVER=0x0A00 _WIN32_WINNT=0x0A00
)

if(MINGW)
  target_link_options(lado_tests PRIVATE -static -static-libgcc -static-libstdc++)
  target_link_options(LadoQaPad PRIVATE -municode -static -static-libgcc -static-libstdc++)
endif()

enable_testing()
add_test(NAME lado_tests COMMAND lado_tests)

install(TARGETS Lado RUNTIME DESTINATION .)
