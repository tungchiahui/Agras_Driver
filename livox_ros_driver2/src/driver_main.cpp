#include <exception>
#include <memory>

#include <rclcpp/rclcpp.hpp>
#include "driver_node.h"

int main(int argc, char* argv[]) {
  rclcpp::init(argc, argv);
  int result = 0;
  try {
    auto node = std::make_shared<livox_ros::DriverNode>(rclcpp::NodeOptions());
    rclcpp::spin(node);
  } catch (const std::exception& error) {
    RCLCPP_ERROR(rclcpp::get_logger("livox_ros_driver2_node"), "%s", error.what());
    result = 1;
  }
  rclcpp::shutdown();
  return result;
}
