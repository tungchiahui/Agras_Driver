cmake_minimum_required(VERSION 3.16)
project(livox_ros_driver2)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
add_compile_definitions(BUILDING_ROS2)
include(cmake/version.cmake)
find_package(ament_cmake_auto REQUIRED)
ament_auto_find_build_dependencies()
find_package(PCL REQUIRED COMPONENTS common io)
find_package(PkgConfig REQUIRED)
pkg_check_modules(APR REQUIRED apr-1)
find_package(Threads REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(std_msgs REQUIRED)

# Build the Agras SDK as part of this ROS package, for the current architecture.
# No global /usr/local SDK installation or prebuilt architecture library is used.
add_subdirectory(third_party/Livox-SDK2/sdk_core)
target_link_libraries(livox_lidar_sdk_shared PRIVATE Threads::Threads)
# A globally installed stock SDK must not override the Agras implementation
# when /usr/local/lib comes first in LD_LIBRARY_PATH.
set_target_properties(livox_lidar_sdk_shared PROPERTIES
  OUTPUT_NAME agras_livox_lidar_sdk_shared
  BUILD_RPATH_USE_ORIGIN TRUE)
if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
  # The SDK bundles an older header-only spdlog. Keep its C++ implementation
  # private so ROS's system spdlog cannot preempt its logger/destructor symbols.
  set(agras_sdk_exports "${CMAKE_CURRENT_SOURCE_DIR}/cmake/agras_sdk.exports")
  target_link_options(livox_lidar_sdk_shared PRIVATE
    "LINKER:--version-script=${agras_sdk_exports}")
  set_property(TARGET livox_lidar_sdk_shared APPEND PROPERTY
    LINK_DEPENDS "${agras_sdk_exports}")
endif()

rosidl_generate_interfaces(livox_interfaces2
  "msg/CustomPoint.msg" "msg/CustomMsg.msg"
  DEPENDENCIES builtin_interfaces std_msgs
  LIBRARY_NAME ${PROJECT_NAME})

ament_auto_add_library(${PROJECT_NAME} SHARED
    src/livox_ros_driver2.cpp
    src/lddc.cpp
    src/driver_node.cpp
    src/sdk_diagnostics.cpp
    src/lds.cpp
    src/lds_lidar.cpp

    src/ext_imu_bridge.cpp

    src/comm/comm.cpp
    src/comm/ldq.cpp
    src/comm/semaphore.cpp
    src/comm/lidar_imu_data_queue.cpp
    src/comm/cache_index.cpp
    src/comm/pub_handler.cpp

    src/parse_cfg_file/parse_cfg_file.cpp
    src/parse_cfg_file/parse_livox_lidar_cfg.cpp

    src/call_back/lidar_common_callback.cpp
    src/call_back/livox_lidar_callback.cpp
)
target_compile_options(${PROJECT_NAME} PRIVATE -Wall -Wextra -Wno-unused-parameter)
target_compile_definitions(${PROJECT_NAME} PRIVATE
  AGRAS_SDK_LIBRARY_NAME="$<TARGET_FILE_NAME:livox_lidar_sdk_shared>")
target_include_directories(${PROJECT_NAME} PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
  ${PCL_INCLUDE_DIRS} ${APR_INCLUDE_DIRS})
target_include_directories(${PROJECT_NAME} PRIVATE 3rdparty src)
rosidl_get_typesupport_target(cpp_typesupport_target livox_interfaces2 rosidl_typesupport_cpp)
target_link_libraries(${PROJECT_NAME}
  ${cpp_typesupport_target} livox_lidar_sdk_shared
  ${PCL_LIBRARIES} ${APR_LIBRARIES} Threads::Threads ${CMAKE_DL_LIBS})
set_target_properties(${PROJECT_NAME} PROPERTIES
  BUILD_RPATH_USE_ORIGIN TRUE
  INSTALL_RPATH "$ORIGIN"
  INSTALL_RPATH_USE_LINK_PATH FALSE)
rclcpp_components_register_nodes(${PROJECT_NAME} "livox_ros::DriverNode")
# The standard component-generated main dlopens the driver by name through a
# ROS library, whose RUNPATH cannot locate this package after relocation.
# Link the standalone entry directly so its own relative RUNPATH is sufficient.
ament_auto_add_executable(${PROJECT_NAME}_node src/driver_main.cpp)
set_target_properties(${PROJECT_NAME}_node PROPERTIES
  BUILD_RPATH_USE_ORIGIN TRUE
  INSTALL_RPATH "$ORIGIN/.."
  INSTALL_RPATH_USE_LINK_PATH FALSE)
ament_auto_package(INSTALL_TO_SHARE config launch)
