# Agras MID360 ROS2 包集合

将整个 `Agras_Driver` 放进 ROS2 工作区的 `src/`，然后使用标准 `colcon` 和 `ros2 launch`。
外层目录不单独构成 ROS 包，也不包含自己的 `build/install/log`。

```text
ros_ws/
├── src/
│   └── Agras_Driver/
│       ├── livox_ros_driver2/     # 驱动与内置 Agras Livox-SDK2 源码
│       ├── fast_lio/              # FAST-LIO2 ROS2 适配
│       ├── lidar_imu_init/         # LI-Init 标定
│       ├── fc_ext_imu_verify/      # 飞控与外置 IMU 对比工具
│       └── agras_bringup/          # 组合启动与参数配置
├── build/
├── install/
└── log/
```

## 编译

环境：Ubuntu 22.04 / ROS2 Humble，或提供同样环境的 Docker 容器。
在工作区根目录执行（目录名不同可替换 `src/Agras_Driver`）：

```bash
source /opt/ros/humble/setup.bash
rosdep install --from-paths src/Agras_Driver --ignore-src --rosdistro humble -y
colcon build --symlink-install --executor sequential \
  --cmake-args -DCMAKE_BUILD_TYPE=Release
source install/setup.bash
```

SDK 随 `livox_ros_driver2` 自动从源码编译，安装在该包的 `install` 前缀内。
库名为 `libagras_livox_lidar_sdk_shared.so`，与系统中可能存在的标准 Livox SDK 区分；
同时只导出 SDK 的公共 C 接口，隔离其内置日志库与 ROS 日志库的符号。
驱动启动时会打印 `Agras SDK library: ...` 实际路径和 `Agras SDK version: ...` 版本。
Linux 下若 SDK 初始化接口被其他库覆盖，启动自检会报告路径并停止启动。
无需单独安装 SDK、复制 `.so`、运行仓库启动脚本或按 CPU 架构选择预编译库。
内存较少时可先 `export MAKEFLAGS=-j1` 限制单个包内的编译并行度。
目标工作区若已有同名 `livox_ros_driver2`、`fast_lio` 等包，需要先选择保留哪一份实现，避免重复包名。

发布到其他电脑时使用普通 `colcon build`（不带 `--symlink-install`），并保持安装目录结构。
正式安装的驱动库使用 `$ORIGIN` RUNPATH 寻找同目录的魔改 SDK，节点入口使用 `$ORIGIN/..`；
开发构建也使用相对的工作区内部库路径。符号链接安装仍依赖原来的源码和构建目录，不能只复制 `install/`。
目标电脑仍需安装对应 ROS2 与系统依赖，并加载 ROS2/工作区环境；SDK 随驱动部署，官方 SDK 可同时保留。

## 启动

每次新开终端先加载 ROS2 与当前工作区环境。下列模式分别运行；切换前关闭上一种模式。

```bash
# 单独启动雷达，默认使用内置 IMU
ros2 launch agras_bringup driver.launch.py

# 雷达 + RViz 原始点云
ros2 launch agras_bringup view.launch.py

# 雷达 + FAST-LIO2 + RViz
ros2 launch agras_bringup fast_lio2.launch.py

# 雷达 + LI-Init 标定 + RViz
ros2 launch agras_bringup calibration.launch.py
```

常用参数：

```bash
# 无显示器
ros2 launch agras_bringup fast_lio2.launch.py rviz:=false

# 替换雷达网络配置（真实设备仍需遵守固件固定地址）
ros2 launch agras_bringup driver.launch.py config:=/absolute/path/AGRAS_MID360_config.json

# 替换算法参数，指定可写输出目录
ros2 launch agras_bringup fast_lio2.launch.py \
  params_file:=/absolute/path/fast_lio2.yaml output_dir:=/absolute/path/results
```

各算法包也保留独立入口（需要另行运行驱动）：

```bash
ros2 launch livox_ros_driver2 driver.launch.py
ros2 launch fast_lio mapping.launch.py
ros2 launch lidar_imu_init agras_mid360.launch.py
```

`fast_lio` 是现有 ROS 包名，`fast_lio2.launch.py` 明确表示组合运行 FAST-LIO2。
当前功能为激光惯性里程计及点云建图；未包含回环优化或完整 Nav2 导航。

## 点云与 IMU 频率

驱动、原始点云查看和 FAST-LIO2 组合入口默认点云目标为 **20 Hz**，约积累 50 ms 的点后发布。
CustomMsg 和 PointCloud2 来自同一帧，采用相同的目标频率；单帧点数随积累时间缩短而减少，
不会因此提高雷达本身每秒产生的点数。当前分帧由数据包到达触发，不保证严格每 50 ms 发布。

内置 IMU 收到一条发布一条，不插值、不重复、不强制降采样到 180 Hz。
原作者记录的 Agras 内置 IMU 频率约为 **184 Hz**，点云帧率为 25～33 Hz 动态；
这些是作者对设备的记录，与本仓库的 ROS 点云发布目标应分别理解，实际设备频率仍需测量。
FAST-LIO2 按时间戳取对应的 IMU 数据，不要求每帧点云包含固定条数的 IMU 测量。

```bash
# 临时切回 10 Hz 查看原始点云
ros2 launch agras_bringup view.launch.py publish_freq:=10.0

# 实物接通后分别检查两个频率（另一个已加载工作区的终端）
ros2 topic hz /livox/lidar/pointcloud
ros2 topic hz /livox/imu
```

FAST-LIO2 默认参数中的 `preprocess.scan_rate` 为 20；改变点云频率时，应使用相应算法参数文件。
`calibration.launch.py` 单独固定驱动目标为 **10 Hz**，与 `calibration.yaml` 的
`initialization.orig_odom_freq: 10` 保持一致，不跟随普通驱动的新默认值。
单独运行 LI-Init 时，也需要将另行启动的驱动设置为 `publish_freq:=10.0`。

## 话题和坐标系

默认 `xfer_format:=4`，一个驱动从同一帧发布：

| 话题 | 类型 | 用途 |
|---|---|---|
| `/livox/lidar` | `livox_ros_driver2/msg/CustomMsg` | FAST-LIO2、LI-Init |
| `/livox/lidar/pointcloud` | `sensor_msgs/msg/PointCloud2` | 原始点云显示 |
| `/livox/imu` | `sensor_msgs/msg/Imu` | 内置或选定的外置 IMU，角速度 rad/s、加速度 m/s² |

单格式兼容模式：`xfer_format:=0` 在 `/livox/lidar` 发布 PointCloud2；
`xfer_format:=1` 在该话题发布 CustomMsg。组合入口固定使用双格式，避免改换消息类型。

原始雷达与 IMU 默认 frame 为 `livox_frame`。FAST-LIO2 输出世界系 `map`、IMU 本体系 `body`，
发布 `map → body → livox_frame`，雷达到 IMU 的外参来自算法参数。
原始查看模式的 `view_origin` 仅为 RViz 提供显示参考，不会在 SLAM 模式发布。
日志、地图及标定结果默认保存到 `~/.ros/agras/fast_lio2` 或 `~/.ros/agras/calibration`，
可通过 `output_dir` 指定；不再写入源码目录。地图保存默认关闭，按参数启用。

## 定制雷达与外置 IMU

Agras 配置：雷达 `192.168.1.10`，主机雷达网卡 `192.168.1.20/24`，
UDP 命令/推送 `60000`、点云 `60001`、IMU `60003`。启动文件不会自动配置网卡。
驱动保留 Agras 适配与 50 m 距离过滤。SDK 来源与本地修改见 `livox_ros_driver2/third_party/README.md`。

供电、极性和定制 Type-C 针脚必须按实际设备可靠定义确认；该接口不可按普通 USB-C 接入。

外置 IMU 可由驱动参数 `ext_imu:=true ext_imu_port:=/dev/ttyIMU` 启用。
组合运行外置 IMU 时还需提供对应算法外参配置，例如包内 `fast_lio/config/agras_mid360_ext.yaml`，
并确认单位、安装方向和时间同步；默认仍为内置 IMU。
`fc_ext_imu_verify` 的独立验证入口仍保留，需要实际 MAVROS 数据源，本集合不自动启动飞控链路。

## Docker（可选环境）

根目录 Dockerfile 只准备开发依赖，源码与工作区在容器中照常编译：

```bash
docker build -t agras-ros2-dev:humble src/Agras_Driver
docker run --rm -it --network host \
  -v "$PWD:/ws" -w /ws agras-ros2-dev:humble
```

容器内执行相同的 `colcon build`、`source install/setup.bash` 和 `ros2 launch`。
上述示例适合无图形入口（`rviz:=false`）；RViz 还需按本机环境传入显示连接和认证。
源码支持在目标平台原生构建；ARM64/树莓派的实际编译与运行状态以验证记录为准。

## 开发验证

### 启动成功但没有 IMU、RViz 无点云

先确认实际数据：话题出现在列表中不代表有消息，RViz 的订阅也可能使话题出现在列表中。
驱动在收到首条 IMU 数据后才创建 `/livox/imu` 发布器。

```bash
ros2 topic hz /livox/lidar/pointcloud
ros2 topic hz /livox/imu
ss -lunp | rg ':(60001|60003)\b'
```

若雷达 `192.168.1.10` 可达、主机地址为 `192.168.1.20/24`，但驱动只监听 `56000`，
检查运行进程实际加载的 SDK：

```bash
pgrep -af livox_ros_driver2_node
# 将下面的 PID 替换为驱动进程号
rg 'livox.*sdk.*so' /proc/PID/maps
```

旧版构建可能受 `LD_LIBRARY_PATH` 顺序影响，误加载 `/usr/local/lib/liblivox_lidar_sdk_shared.so`，
导致初始化提示成功但收不到 Agras 数据。停止旧驱动，用当前源码重新编译
`colcon build --symlink-install --packages-select livox_ros_driver2`，重新加载工作区并启动。
修复后的进程应加载本工作区的 `libagras_livox_lidar_sdk_shared.so`。
启动日志中的 `Agras SDK library:` 会直接给出该库的实际路径；符号链接安装会显示构建目录下的真实文件。
仅需临时恢复旧构建时，可在启动前把本包库目录置于最前：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
export LD_LIBRARY_PATH="$(ros2 pkg prefix livox_ros_driver2)/lib:$LD_LIBRARY_PATH"
ros2 launch agras_bringup view.launch.py
```

RViz 使用 `/livox/lidar/pointcloud`，Fixed Frame 为 `livox_frame`，Reliability 为 Best Effort。

### 离线回归

`tools/tests/` 只供开发时做离线回归，不是用户编译或启动的前置步骤。
运行前加载已编译工作区；使用回环配置和独立 ROS_DOMAIN_ID，避免干扰其他 ROS 会话。
RViz 自动显示测试另需 Xvfb；常规启动不需要它。
旧入口参考保存在 `docs/legacy_launch/`，不安装为当前 launch。
`smoke_test.py` 包含官方同名库优先、启动路径日志、错误 SDK 接口覆盖和正常退出检查。
使用普通安装后，可额外运行迁移验证：

```bash
python3 tools/tests/sdk_relocation_test.py /absolute/path/to/install/livox_ros_driver2
```

该检查将包内库复制到临时目录，在库搜索路径中只保留 ROS2、系统与模拟旧 SDK 路径，
确认驱动通过相对 RUNPATH 加载迁移后的魔改 SDK，并正常退出。

## 原作者 README

原文按导入改造前的作者提交 `b0ba8cd24113b0e21db7ec63b556d5d4b8a95e77` 保留在对应包内，
不改写原文；历史说明中的构建、启动命令及功能描述以本页当前用法为准。

| 原文 | 当前位置 |
|---|---|
| Agras 原仓库总说明（含定制固件差异和作者频率记录） | [livox_ros_driver2/README.agras-original.md](livox_ros_driver2/README.agras-original.md) |
| Livox 驱动原说明 | [livox_ros_driver2/README.md](livox_ros_driver2/README.md) |
| FAST-LIO 原说明 | [fast_lio/README.upstream.md](fast_lio/README.upstream.md) |
| LI-Init 原说明 | [lidar_imu_init/README.md](lidar_imu_init/README.md) |
| 外置 IMU 对比工具原说明 | [fc_ext_imu_verify/README.md](fc_ext_imu_verify/README.md) |
