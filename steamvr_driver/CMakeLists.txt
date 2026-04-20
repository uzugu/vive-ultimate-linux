cmake_minimum_required(VERSION 3.20)
project(ultimate_tracker_linux_driver LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

set(DRIVER_NAME ultimate_tracker_linux)
set(OPENVR_SDK_PATH "" CACHE PATH "Path to the OpenVR SDK checkout")

if(NOT OPENVR_SDK_PATH)
    message(FATAL_ERROR "OPENVR_SDK_PATH must point at a local OpenVR SDK checkout.")
endif()

find_path(OPENVR_INCLUDE_DIR
    NAMES openvr_driver.h
    PATHS "${OPENVR_SDK_PATH}/headers"
    NO_DEFAULT_PATH
)

find_library(OPENVR_API_LIB
    NAMES openvr_api libopenvr_api.a
    PATHS "${OPENVR_SDK_PATH}/lib/linux64"
    NO_DEFAULT_PATH
)

if(NOT OPENVR_INCLUDE_DIR)
    message(FATAL_ERROR "Failed to find openvr_driver.h under ${OPENVR_SDK_PATH}/headers")
endif()

if(NOT OPENVR_API_LIB)
    message(FATAL_ERROR "Failed to find the OpenVR library under ${OPENVR_SDK_PATH}/lib/linux64")
endif()

add_library(driver_${DRIVER_NAME} SHARED
    src/device_provider.cpp
    src/driver_factory.cpp
    src/ipc_pose_client.cpp
    src/ultimate_tracker_device.cpp
)

target_include_directories(driver_${DRIVER_NAME} PRIVATE
    include
    ${OPENVR_INCLUDE_DIR}
)

target_link_libraries(driver_${DRIVER_NAME} PRIVATE
    ${OPENVR_API_LIB}
)

set_target_properties(driver_${DRIVER_NAME} PROPERTIES
    OUTPUT_NAME "driver_${DRIVER_NAME}"
    PREFIX ""
)

set(STAGE_ROOT "${CMAKE_BINARY_DIR}/stage/${DRIVER_NAME}")
set(STAGE_BIN_DIR "${STAGE_ROOT}/bin/linux64")

add_custom_command(TARGET driver_${DRIVER_NAME} POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E make_directory "${STAGE_BIN_DIR}"
    COMMAND ${CMAKE_COMMAND} -E copy "$<TARGET_FILE:driver_${DRIVER_NAME}>" "${STAGE_BIN_DIR}/$<TARGET_FILE_NAME:driver_${DRIVER_NAME}>"
    COMMAND ${CMAKE_COMMAND} -E copy_directory "${CMAKE_CURRENT_SOURCE_DIR}/resources" "${STAGE_ROOT}/resources"
    COMMAND ${CMAKE_COMMAND} -E copy "${CMAKE_CURRENT_SOURCE_DIR}/driver/${DRIVER_NAME}/driver.vrdrivermanifest" "${STAGE_ROOT}/driver.vrdrivermanifest"
)

