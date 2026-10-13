# BLT's own build of OpenUtau's worldline.dll from the pinned sources (see docs/worldline-provenance.md).
# Laid out by prepare.py. PATCH_SPLINE=ON (the product) replaces the GPL tk::spline.
cmake_minimum_required(VERSION 3.20)
project(blt_worldline C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreadedDLL")
option(PATCH_SPLINE "use BLT's own spline instead of the GPL tk::spline (the product)" ON)
set(ABSL_PROPAGATE_CXX_STD ON)
set(ABSL_BUILD_TESTING OFF)
add_subdirectory(wl/abseil absl EXCLUDE_FROM_ALL)

set(WL ${CMAKE_CURRENT_SOURCE_DIR}/worldline-src/cpp)
file(GLOB WORLD_SRC wl/world/src/*.cpp)
file(GLOB GVPS_SRC wl/libgvps/*.c)
file(GLOB PYIN_SRC wl/libpyin/*.c)
file(GLOB F0_SRC ${WL}/worldline/f0/*.cpp)
file(GLOB PLAT_SRC ${WL}/worldline/platinum/*.cpp)

if(PATCH_SPLINE)
  set(EFFECTS_SRC ${CMAKE_CURRENT_SOURCE_DIR}/patched/worldline/model/effects.cpp)
else()
  set(EFFECTS_SRC ${WL}/worldline/model/effects.cpp)
endif()

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
  ${EFFECTS_SRC}
  ${WL}/worldline/audio_output.cc
  wl/xxhash/xxhash.c
)
target_include_directories(worldline PRIVATE
  ${WL} wl wl/world/src wl/world/tools wl/libpyin wl/libgvps wl/spline/src wl/libnpy/include wl/miniaudio wl/xxhash)
target_compile_definitions(worldline PRIVATE FP_TYPE=double _CRT_SECURE_NO_WARNINGS $<$<COMPILE_LANGUAGE:CXX>:NOMINMAX>)
target_link_libraries(worldline PRIVATE absl::strings)
if(MSVC)
  target_compile_options(worldline PRIVATE /O2 /Gy /Brepro)
  target_link_options(worldline PRIVATE /MAP /OPT:REF /OPT:ICF /Brepro)
endif()
set_target_properties(worldline PROPERTIES PREFIX "" WINDOWS_EXPORT_ALL_SYMBOLS OFF)
if(PATCH_SPLINE)
  target_include_directories(worldline BEFORE PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/patched)
  # the GPL spline header is not on the include path at all in this variant
  get_target_property(_inc worldline INCLUDE_DIRECTORIES)
  list(FILTER _inc EXCLUDE REGEX "wl/spline/src")
  set_target_properties(worldline PROPERTIES INCLUDE_DIRECTORIES "${_inc}")
endif()
