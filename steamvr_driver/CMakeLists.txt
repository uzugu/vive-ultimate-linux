cmake_minimum_required(VERSION 3.20)
project(ultimate_tracker_linux_driver LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

set(DRIVER_NAME ultimate_tracker_linux)
set(OPENVR_SDK_PATH "" CACHE PATH "Path to the OpenVR SDK checkout")
option(UTS_BUILD_DRIVER "Build the SteamVR driver (needs the OpenVR SDK)" ON)
option(UTS_BUILD_TESTS "Build the OpenVR-free unit tests" OFF)

# Pose socket client and parser: no OpenVR dependency, shared by the driver and the tests.
add_library(uts_ipc STATIC src/ipc_pose_client.cpp src/calibration.cpp)
target_include_directories(uts_ipc PUBLIC include)
if(WIN32)
    target_link_libraries(uts_ipc PUBLIC ws2_32)
endif()

if(UTS_BUILD_TESTS)
    enable_testing()
    add_executable(ipc_pose_client_test tests/ipc_pose_client_test.cpp)
    target_link_libraries(ipc_pose_client_test PRIVATE uts_ipc)
    target_compile_definitions(ipc_pose_client_test PRIVATE
        UTS_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/../protocol/fixtures")
    add_test(NAME ipc_pose_client COMMAND ipc_pose_client_test)

    add_executable(calibration_test tests/calibration_test.cpp)
    target_link_libraries(calibration_test PRIVATE uts_ipc)
    add_test(NAME calibration COMMAND calibration_test)
endif()

if(NOT UTS_BUILD_DRIVER)
    return()
endif()

if(NOT OPENVR_SDK_PATH)
    message(FATAL_ERROR "OPENVR_SDK_PATH must point at a local OpenVR SDK checkout.")
endif()

find_path(OPENVR_INCLUDE_DIR
    NAMES openvr_driver.h
    PATHS "${OPENVR_SDK_PATH}/headers"
    NO_DEFAULT_PATH
)

if(WIN32)
    set(OPENVR_PLATFORM win64)
else()
    set(OPENVR_PLATFORM linux64)
endif()

find_library(OPENVR_API_LIB
    NAMES openvr_api libopenvr_api.a
    PATHS "${OPENVR_SDK_PATH}/lib/${OPENVR_PLATFORM}"
    NO_DEFAULT_PATH
)

if(NOT OPENVR_INCLUDE_DIR)
    message(FATAL_ERROR "Failed to find openvr_driver.h under ${OPENVR_SDK_PATH}/headers")
endif()

if(NOT OPENVR_API_LIB)
    message(FATAL_ERROR "Failed to find the OpenVR library under ${OPENVR_SDK_PATH}/lib/${OPENVR_PLATFORM}")
endif()

add_library(driver_${DRIVER_NAME} SHARED
    src/device_provider.cpp
    src/driver_factory.cpp
    src/ultimate_tracker_device.cpp
)

target_include_directories(driver_${DRIVER_NAME} PRIVATE
    include
    ${OPENVR_INCLUDE_DIR}
)

target_link_libraries(driver_${DRIVER_NAME} PRIVATE
    uts_ipc
    ${OPENVR_API_LIB}
)

set_target_properties(driver_${DRIVER_NAME} PROPERTIES
    OUTPUT_NAME "driver_${DRIVER_NAME}"
    PREFIX ""
)

set(STAGE_ROOT "${CMAKE_BINARY_DIR}/stage/${DRIVER_NAME}")
set(STAGE_BIN_DIR "${STAGE_ROOT}/bin/${OPENVR_PLATFORM}")

add_custom_command(TARGET driver_${DRIVER_NAME} POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E make_directory "${STAGE_BIN_DIR}"
    COMMAND ${CMAKE_COMMAND} -E copy "$<TARGET_FILE:driver_${DRIVER_NAME}>" "${STAGE_BIN_DIR}/$<TARGET_FILE_NAME:driver_${DRIVER_NAME}>"
    COMMAND ${CMAKE_COMMAND} -E copy_directory "${CMAKE_CURRENT_SOURCE_DIR}/resources" "${STAGE_ROOT}/resources"
    COMMAND ${CMAKE_COMMAND} -E copy "${CMAKE_CURRENT_SOURCE_DIR}/driver/${DRIVER_NAME}/driver.vrdrivermanifest" "${STAGE_ROOT}/driver.vrdrivermanifest"
)

