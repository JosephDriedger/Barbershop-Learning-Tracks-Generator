# BLT's own build of OpenUtau's worldline.dll from the pinned sources (see docs/worldline-provenance.md).
# Laid out by prepare.py. The tension effect is not part of this build: patched/worldline/model/effects.cpp
# (upstream effects.cpp + effects-no-tension-spline.patch) returns the neutral envelope, so no spline library
# is downloaded, compiled or on any include path.
cmake_minimum_required(VERSION 3.20)
project(blt_worldline C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreadedDLL")
if(APPLE)
  # the oldest macOS the .NET 8 host runs on
  if(NOT CMAKE_OSX_DEPLOYMENT_TARGET)
    set(CMAKE_OSX_DEPLOYMENT_TARGET "12.0")
  endif()
endif()
if(NOT MSVC)
  # only the functions marked DLL_API leave the library (Abseil and the rest are linked in, not exported)
  set(CMAKE_C_VISIBILITY_PRESET hidden)
  set(CMAKE_CXX_VISIBILITY_PRESET hidden)
  set(CMAKE_VISIBILITY_INLINES_HIDDEN ON)
  set(CMAKE_POSITION_INDEPENDENT_CODE ON)
endif()
set(ABSL_PROPAGATE_CXX_STD ON)
set(ABSL_BUILD_TESTING OFF)
add_subdirectory(wl/abseil absl EXCLUDE_FROM_ALL)

set(WL ${CMAKE_CURRENT_SOURCE_DIR}/worldline-src/cpp)
file(GLOB WORLD_SRC wl/world/src/*.cpp)
file(GLOB GVPS_SRC wl/libgvps/*.c)
file(GLOB PYIN_SRC wl/libpyin/*.c)
file(GLOB F0_SRC ${WL}/worldline/f0/*.cpp)
file(GLOB PLAT_SRC ${WL}/worldline/platinum/*.cpp)

add_library(worldline SHARED
  ${WORLD_SRC} ${GVPS_SRC} ${PYIN_SRC} ${F0_SRC} ${PLAT_SRC}
  wl/world/tools/audioio.cpp
  ${WL}/worldline/worldline.cpp
  ${WL}/worldline/phrase_synth.cpp
  ${WL}/worldline/classic/classic_args.cpp
  ${WL}/worldline/classic/frq.cpp
  ${WL}/worldline/classic/resampler.cpp
  ${WL}/worldline/classic/timing.cpp
  ${WL}/worldline/common/vec_utils.cpp
  ${WL}/worldline/model/model.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/patched/worldline/model/effects.cpp
  ${WL}/worldline/audio_output.cc
  wl/xxhash/xxhash.c
)
target_include_directories(worldline PRIVATE
  ${WL} wl wl/world/src wl/world/tools wl/libpyin wl/libgvps wl/libnpy/include wl/miniaudio wl/xxhash)
target_compile_definitions(worldline PRIVATE FP_TYPE=double _CRT_SECURE_NO_WARNINGS $<$<COMPILE_LANGUAGE:CXX>:NOMINMAX>)
target_link_libraries(worldline PRIVATE absl::strings)
if(MSVC)
  target_compile_options(worldline PRIVATE /O2 /Gy /Brepro)
  target_link_options(worldline PRIVATE /MAP /OPT:REF /OPT:ICF /Brepro)
endif()
if(WIN32)
  set_target_properties(worldline PROPERTIES PREFIX "" WINDOWS_EXPORT_ALL_SYMBOLS OFF)
elseif(APPLE)
  # libworldline.dylib, the name OpenUtau.Core's [DllImport("worldline")] finds on macOS; a link map for verify_dylib.py
  target_compile_options(worldline PRIVATE -O2 -ffunction-sections -fdata-sections)
  target_link_options(worldline PRIVATE -Wl,-dead_strip -Wl,-map,${CMAKE_CURRENT_BINARY_DIR}/worldline.map)
endif()
