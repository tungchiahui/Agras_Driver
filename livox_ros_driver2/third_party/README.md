# Agras Livox-SDK2

`Livox-SDK2/` was restored from A908gao/Agras_Driver:

- Commit: `a8ec100cd369bb038e586bf3617fd169f56db0c1`
- SDK tree: `d71559871e1eab9961e11ff30eb0dc0d28f116a5`
- Source: <https://github.com/A908gao/Agras_Driver/tree/a8ec100cd369bb038e586bf3617fd169f56db0c1/Livox-SDK2>
- Historical file manifest: repository `docs/sdk-source.json` (222 files).

The original snapshot was independently verified against the GitHub tree and
SHA256 manifest before integration. The manifest describes that original snapshot.

Local changes are confined to:

1. `sdk_core/CMakeLists.txt`: the ROS2 package builds and installs the shared SDK
   library; its unused static target is excluded from the default build.
2. `sdk_core/data_handler/data_handler.cpp`: reject incomplete/invalid MID360
   datagrams before invoking driver callbacks (header length, data type, version,
   and point-count bounds). IMU payload size is validated independently of the
   point-count field, which custom firmware may leave unset.

The author's Agras-specific port and discovery handling is retained. Licenses
and third-party notices remain in the vendored source. No global SDK installation,
download step, firmware update, or precompiled architecture binary is required.

The parent ROS2 package gives the shared library the distinct output name
`libagras_livox_lidar_sdk_shared.so` so a globally installed stock SDK cannot
override it through `LD_LIBRARY_PATH`. On Linux, `cmake/agras_sdk.exports` in the
ROS2 package exports only the public C API and keeps the bundled spdlog/fmt C++
symbols private, preventing ABI collisions with ROS's system logging libraries.
The parent package also assigns relative build/install RUNPATHs and verifies the
resolved SDK initialization entry point before starting devices or worker threads.
Startup logs show the canonical library path and the SDK's numeric version.
