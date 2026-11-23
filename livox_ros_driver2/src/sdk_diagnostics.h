#ifndef LIVOX_ROS_DRIVER2_SDK_DIAGNOSTICS_H_
#define LIVOX_ROS_DRIVER2_SDK_DIAGNOSTICS_H_

#include <rclcpp/logger.hpp>

namespace livox_ros {

// Verify the resolved SDK entry point before starting any device or worker.
void VerifyAgrasSdkLibrary(const rclcpp::Logger& logger);

}  // namespace livox_ros

#endif  // LIVOX_ROS_DRIVER2_SDK_DIAGNOSTICS_H_
