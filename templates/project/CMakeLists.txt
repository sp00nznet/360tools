# Vigilante 8 Arcade - ReXGlue Static Recompilation Project
cmake_minimum_required(VERSION 3.25)
project(vig8 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Find ReXGlue SDK
if(DEFINED ENV{REXSDK})
    set(REXSDK_PATH "$ENV{REXSDK}")
else()
    # Default to our local SDK build
    set(REXSDK_PATH "${CMAKE_SOURCE_DIR}/../tools/rexglue-sdk/out/install/win-amd64")
endif()
list(APPEND CMAKE_PREFIX_PATH "${REXSDK_PATH}")

find_package(rexglue REQUIRED)

# Include generated source list
include(${CMAKE_SOURCE_DIR}/../generated/sources.cmake)

# Platform entry point from SDK
if(WIN32)
    set(ENTRY_POINT_SRC "${REXSDK_PATH}/share/rexglue/windowed_app_main_win.cpp")
else()
    set(ENTRY_POINT_SRC "${REXSDK_PATH}/share/rexglue/windowed_app_main_posix.cpp")
endif()

# Main executable
if(WIN32)
    add_executable(vig8 WIN32
        src/main.cpp
        src/stubs.cpp
        src/settings.cpp
        src/menu.cpp
        src/net.cpp
        ${ENTRY_POINT_SRC}
        ${GENERATED_SOURCES}
    )
else()
    add_executable(vig8
        src/main.cpp
        src/stubs.cpp
        src/settings.cpp
        src/menu.cpp
        src/net.cpp
        ${ENTRY_POINT_SRC}
        ${GENERATED_SOURCES}
    )
endif()

target_include_directories(vig8 PRIVATE
    ${CMAKE_SOURCE_DIR}/../generated
)

target_link_libraries(vig8 PRIVATE
    rex::core
    rex::runtime
    rex::kernel
    rex::graphics
    rex::ui
)

# Compile options matching rexglue requirements
target_compile_options(vig8 PRIVATE
    -fno-strict-aliasing
    -ffp-model=strict
    -fno-char8_t
    $<$<CONFIG:DEBUG>:-g>
    $<$<CONFIG:DEBUG>:-O0>
    $<$<CONFIG:RELEASE>:-O3>
    $<$<CONFIG:RELEASE>:-DNDEBUG>
)

if(NOT MSVC)
    target_compile_options(vig8 PRIVATE -msse4.1)
endif()

# Allow our stubs.cpp to override XAM user functions from rexkernel.lib.
# xam_user.cpp.obj gets pulled in for functions we still need (e.g.
# XamUserReadProfileSettings), so /force:multiple lets our definitions
# take precedence over the library's.
if(WIN32)
    target_link_options(vig8 PRIVATE "LINKER:/force:multiple")
endif()

# Console test executable (no GUI)
add_executable(vig8_test
    src/test_boot.cpp
    src/stubs.cpp
    src/net.cpp
    ${GENERATED_SOURCES}
)
target_include_directories(vig8_test PRIVATE
    ${CMAKE_SOURCE_DIR}/../generated
)
target_link_libraries(vig8_test PRIVATE
    rex::core
    rex::runtime
    rex::kernel
    rex::graphics
    rex::ui
)
target_compile_options(vig8_test PRIVATE
    -fno-strict-aliasing
    -ffp-model=strict
    -fno-char8_t
    $<$<CONFIG:RELEASE>:-O3>
    $<$<CONFIG:RELEASE>:-DNDEBUG>
)
if(NOT MSVC)
    target_compile_options(vig8_test PRIVATE -msse4.1)
endif()

if(WIN32)
    target_link_options(vig8_test PRIVATE "LINKER:/force:multiple")
endif()

# Whole-archive link for kernel hooks on Linux
if(NOT WIN32)
    target_link_options(vig8 PRIVATE
        -Wl,--whole-archive $<TARGET_FILE:rex::kernel> -Wl,--no-whole-archive
    )
    target_compile_options(vig8 PRIVATE -mcmodel=large)
endif()
