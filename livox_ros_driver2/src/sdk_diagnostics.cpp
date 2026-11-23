#include "sdk_diagnostics.h"

#include <cstdlib>
#include <memory>
#include <stdexcept>
#include <string>

#include <rclcpp/logging.hpp>
#include "livox_lidar_api.h"

#if defined(__linux__)
#include <dlfcn.h>
#endif

namespace livox_ros {

void VerifyAgrasSdkLibrary(const rclcpp::Logger& logger) {
#if defined(__linux__)
  Dl_info info{};
  if (dladdr(reinterpret_cast<const void*>(&LivoxLidarSdkInit), &info) == 0 ||
      info.dli_fname == nullptr) {
    RCLCPP_ERROR(logger, "Cannot determine the loaded Agras SDK library path");
    throw std::runtime_error("Agras SDK library verification failed");
  }

  // Resolve symlink installations too, so the log shows the actual binary.
  std::unique_ptr<char, decltype(&std::free)> canonical_path(
      realpath(info.dli_fname, nullptr), &std::free);
  const std::string path = canonical_path ? canonical_path.get() : info.dli_fname;
  RCLCPP_INFO(logger, "Agras SDK library: %s", path.c_str());

  const auto separator = path.find_last_of('/');
  const std::string filename = separator == std::string::npos ? path : path.substr(separator + 1);
  if (filename != AGRAS_SDK_LIBRARY_NAME) {
    RCLCPP_ERROR(logger, "Expected %s, but LivoxLidarSdkInit resolves to %s",
                 AGRAS_SDK_LIBRARY_NAME, path.c_str());
    throw std::runtime_error("Agras SDK library verification failed");
  }
#endif

  LivoxLidarSdkVer version{};
  GetLivoxLidarSdkVer(&version);
  RCLCPP_INFO(logger, "Agras SDK version: %d.%d.%d", version.major, version.minor, version.patch);
}

}  // namespace livox_ros
