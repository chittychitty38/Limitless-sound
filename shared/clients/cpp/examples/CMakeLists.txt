# The example product, built with CMake:
#   cmake -S shared/clients/cpp/examples -B build && cmake --build build
cmake_minimum_required(VERSION 3.14)
project(limitless_link_example CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
find_package(Threads REQUIRED)

add_executable(check check.cpp)
# In your own project: the folder you copied limitless_link.hpp into, then #include "limitless_link.hpp".
target_include_directories(check PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/..)
target_link_libraries(check PRIVATE Threads::Threads $<$<PLATFORM_ID:Windows>:ws2_32>)
