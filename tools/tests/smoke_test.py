#!/usr/bin/env python3
"""Offline UDP -> SDK -> ROS2 integration checks. All traffic stays on loopback."""
import json
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import tempfile
import time

import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Imu, PointCloud2
from ament_index_python.packages import get_package_prefix
from livox_ros_driver2.msg import CustomMsg


ROOT = Path(get_package_prefix('livox_ros_driver2'))
EXE = ROOT / 'lib/livox_ros_driver2/livox_ros_driver2_node'
CONFIG = ROOT / 'share/livox_ros_driver2/config/AGRAS_MID360_config.json'
HEADER = struct.Struct('<BHHHHBBB12sIQ')
RESULTS = []


def packet(kind, payload, count=1, version=1):
    return HEADER.pack(version, HEADER.size + len(payload), 10000, count,
                       0, 0, kind, 0, bytes(12), 0, time.time_ns()) + payload


class Driver:
    def __init__(self, directory, name, config, xfer=0, env=None):
        self.path = Path(directory) / (name + '.json')
        self.path.write_text(json.dumps(config))
        self.log = tempfile.TemporaryFile(mode='w+')
        self.proc = subprocess.Popen([
            str(EXE), '--ros-args', '-p', 'user_config_path:=' + str(self.path),
            '-p', 'xfer_format:=' + str(xfer), '-p', 'frame_id:=livox_frame',
            '-p', 'ext_imu_enable:=false', '-p', 'publish_freq:=10.0',
        ], stdout=self.log, stderr=subprocess.STDOUT, env=env)

    def output(self):
        self.log.seek(0)
        return self.log.read()

    def stop(self):
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGINT)
        try:
            code = self.proc.wait(timeout=7)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
            raise AssertionError('Driver hung during shutdown:\n' + self.output())
        assert code == 0, (code, self.output())


def loopback_config():
    cfg = json.loads(CONFIG.read_text())
    host = cfg['MID360']['host_net_info']
    for key in ('cmd_data_ip', 'push_msg_ip', 'point_data_ip', 'imu_data_ip'):
        host[key] = '127.0.0.1'
    host['lidar_ip'] = ['127.0.0.2']
    cfg['lidar_configs'][0]['ip'] = '127.0.0.2'
    return cfg


def spin(node, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.02)


def stream_check(directory, xfer, standard=False):
    cfg = loopback_config()
    net = cfg['MID360']['lidar_net_info']
    host = cfg['MID360']['host_net_info']
    version = 1
    if standard:
        version = 0
        cfg['MID360']['host_net_info'] = [host]
        net.update(cmd_data_port=56100, push_msg_port=56200,
                   point_data_port=56300, imu_data_port=56400)
        host.update(cmd_data_port=56101, push_msg_port=56201,
                    point_data_port=56301, imu_data_port=56401)
    name = 'standard-v0' if standard else {0: 'agras-pointcloud2', 1: 'agras-custom', 4: 'agras-dual'}[xfer]
    node = rclpy.create_node('smoke_' + name.replace('-', '_'))
    clouds, imus = [], []
    cloud_type = PointCloud2 if xfer == 0 else CustomMsg
    secondary = []
    subs = [node.create_subscription(cloud_type, '/livox/lidar', clouds.append, qos_profile_sensor_data),
            node.create_subscription(Imu, '/livox/imu', imus.append, qos_profile_sensor_data)]
    if xfer == 4:
        subs.append(node.create_subscription(PointCloud2, '/livox/lidar/pointcloud', secondary.append, qos_profile_sensor_data))
    driver = Driver(directory, name, cfg, xfer)
    point_socket, imu_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM), socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    point_socket.bind(('127.0.0.2', net['point_data_port']))
    imu_socket.bind(('127.0.0.2', net['imu_data_port']))
    try:
        spin(node, 4.0)
        assert driver.proc.poll() is None, driver.output()
        # Empty, truncated, zero-point, oversized-count, unsupported-version and
        # short IMU packets must not crash the process or publish bogus samples.
        good = packet(1, struct.pack('<iiiBB', 1000, 2000, 3000, 42, 0x10), version=version)
        bad_packets = [b'', b'\x01', good[:HEADER.size - 1], good[:-1],
                       packet(1, b'', count=0, version=version),
                       packet(1, good[HEADER.size:], count=65535, version=version),
                       packet(1, good[HEADER.size:], version=255)]
        for bad in bad_packets:
            point_socket.sendto(bad, ('127.0.0.1', host['point_data_port']))
        imu_socket.sendto(packet(0, b'\x00', version=version), ('127.0.0.1', host['imu_data_port']))
        spin(node, 0.4)
        assert driver.proc.poll() is None and not clouds and not imus, driver.output()
        # An unconfigured sender must be ignored even with a well-formed packet.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as other:
            other.bind(('127.0.0.3', net['point_data_port']))
            other.sendto(good, ('127.0.0.1', host['point_data_port']))
        spin(node, 0.2)
        assert not clouds and not imus
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            # Each packet has one valid point and a 200 m Agras sentinel.
            points = struct.pack('<iiiBB', 1000, 2000, 3000, 42, 0x10)
            points += struct.pack('<iiiBB', 200000, 0, 0, 0, 0x10)
            point_socket.sendto(packet(1, points, count=2, version=version),
                                ('127.0.0.1', host['point_data_port']))
            imu_socket.sendto(packet(0, struct.pack('<6f', 0.01, -0.02, 0.03, 0, 0, 1), version=version),
                              ('127.0.0.1', host['imu_data_port']))
            rclpy.spin_once(node, timeout_sec=0.005)
            time.sleep(0.005)
        spin(node, 0.2)
        assert len(clouds) >= 5 and len(imus) >= 20, (len(clouds), len(imus), driver.output())
        assert all(msg.header.frame_id == 'livox_frame' for msg in clouds + imus)
        assert all(msg.orientation_covariance[0] == -1.0 for msg in imus)
        if xfer == 4:
            assert len(secondary) >= 5, len(secondary)
            custom_by_stamp = {(m.header.stamp.sec, m.header.stamp.nanosec): m for m in clouds}
            matches = [m for m in secondary if (m.header.stamp.sec, m.header.stamp.nanosec) in custom_by_stamp]
            assert len(matches) >= 5
            assert all(m.width == custom_by_stamp[(m.header.stamp.sec, m.header.stamp.nanosec)].point_num for m in matches)
            assert node.count_publishers('/livox/imu') == 1
        assert all(abs(msg.linear_acceleration.z - 9.8) < 1e-5 for msg in imus)
        assert all(abs(msg.angular_velocity.y + 0.02) < 1e-5 for msg in imus)
        points_checked = 0
        for cloud in clouds:
            if xfer == 0:
                assert cloud.width > 0 and len(cloud.data) == cloud.row_step * cloud.height
                coords = [struct.unpack_from('<fff', cloud.data, i * cloud.point_step) for i in range(cloud.width)]
            else:
                assert cloud.point_num == len(cloud.points) > 0
                coords = [(p.x, p.y, p.z) for p in cloud.points]
                assert all(0 <= p.line < 4 for p in cloud.points)
            assert all(all(abs(a-b) < 1e-5 for a, b in zip(xyz, (1, 2, 3))) for xyz in coords), coords[:3]
            points_checked += len(coords)
        stamps = [m.header.stamp.sec * 10**9 + m.header.stamp.nanosec for m in clouds]
        assert all(b >= a for a, b in zip(stamps, stamps[1:]))
        driver.stop()
        RESULTS.append(dict(check=name, clouds=len(clouds), imus=len(imus),
                            valid_points=points_checked, sentinel_filtered=True,
                            malformed_packets_rejected=True, clean_shutdown=True))
    finally:
        if driver.proc.poll() is None:
            driver.proc.kill()
            driver.proc.wait()
        point_socket.close()
        imu_socket.close()
        node.destroy_node()


def launch_check(directory, node, entry, algorithm=None):
    config = Path(directory) / (entry + '-network.json')
    config.write_text(json.dumps(loopback_config()))
    output_dir = Path(directory) / entry
    command = ['ros2', 'launch', 'agras_bringup', entry + '.launch.py',
               'config:=' + str(config), 'rviz:=false', 'output_dir:=' + str(output_dir)]
    with tempfile.TemporaryFile(mode='w+') as log:
        proc = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True, cwd=directory)
        try:
            spin(node, 5)
            log.seek(0)
            assert proc.poll() is None, log.read()
            names = node.get_node_names()
            assert names.count('livox_lidar_publisher') == 1, names
            assert 'rviz2' not in names, names
            if algorithm:
                assert names.count(algorithm) == 1, names
                assert all((output_dir / subdir).is_dir() for subdir in ('Log', 'PCD', 'result'))
            proc.send_signal(signal.SIGINT)
            assert proc.wait(timeout=10) == 0
            log.seek(0)
            output = log.read()
            assert 'process has died' not in output, output
            RESULTS.append(dict(check='launch-' + entry, passed=True,
                                driver_count=1, rviz_disabled=True, clean_shutdown=True))
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
        spin(node, 0.5)


def main():
    # Launch resolution and both viewer configurations must load without radar.
    for launch in ('driver.launch.py', 'view.launch.py', 'fast_lio2.launch.py', 'calibration.launch.py'):
        subprocess.run(['ros2', 'launch', 'agras_bringup', launch, '--show-args'],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
    for library in (ROOT / 'lib').rglob('*.so'):
        result = subprocess.check_output(['ldd', str(library)], text=True)
        assert 'not found' not in result, result
    RESULTS.append(dict(check='launch-and-linker', passed=True))
    rclpy.init()
    try:
        with tempfile.TemporaryDirectory() as directory:
            # Reproduce a legacy SDK ahead of the workspace in the search path.
            # An invalid legacy file makes accidental selection fail immediately.
            legacy = Path(directory) / 'legacy-sdk'
            legacy.mkdir()
            (legacy / 'liblivox_lidar_sdk_shared.so').write_text('not the Agras SDK\n')
            env = dict(os.environ, LD_LIBRARY_PATH=str(legacy) + ':/usr/local/lib:' +
                       os.environ.get('LD_LIBRARY_PATH', ''))
            idle = Driver(directory, 'idle', loopback_config(), env=env)
            time.sleep(4)
            assert idle.proc.poll() is None, idle.output()
            maps = Path('/proc/{}/maps'.format(idle.proc.pid)).read_text()
            sdk = (ROOT / 'lib/libagras_livox_lidar_sdk_shared.so').resolve()
            assert str(sdk) in maps, maps
            assert 'liblivox_lidar_sdk_shared.so' not in maps, maps
            output = idle.output()
            assert 'Agras SDK library: ' + str(sdk) in output, output
            assert 'Agras SDK version: ' in output, output
            idle.stop()
            RESULTS.append(dict(check='bundled-sdk-priority', passed=True,
                                legacy_sdk_shadow_ignored=True))
            RESULTS.append(dict(check='no-radar-start-stop', passed=True))
            # A preloaded SDK can interpose C symbols even with a distinct
            # SONAME. Verify that startup rejects the wrong implementation.
            shim = legacy / 'libwrong-sdk.so'
            subprocess.run(['cc', '-shared', '-fPIC', '-x', 'c', '-', '-o', str(shim)],
                           input='_Bool LivoxLidarSdkInit(void) { return 0; }\n',
                           text=True, check=True, capture_output=True)
            wrong = Driver(directory, 'wrong-sdk', loopback_config(),
                           env=dict(os.environ, LD_PRELOAD=str(shim)))
            try:
                code = wrong.proc.wait(timeout=8)
                output = wrong.output()
                assert code != 0, output
                assert 'Agras SDK library: ' + str(shim) in output, output
                assert 'Agras SDK library verification failed' in output, output
                assert 'Init lds lidar success' not in output, output
            finally:
                if wrong.proc.poll() is None:
                    wrong.proc.kill()
                    wrong.proc.wait()
            RESULTS.append(dict(check='wrong-sdk-rejected', passed=True))
            stream_check(directory, 0)
            stream_check(directory, 1)
            stream_check(directory, 4)
            stream_check(directory, 0, standard=True)
            # An unavailable host address must fail clearly rather than look healthy.
            invalid_cfg = loopback_config()
            for key in ('cmd_data_ip', 'push_msg_ip', 'point_data_ip', 'imu_data_ip'):
                invalid_cfg['MID360']['host_net_info'][key] = '192.0.2.123'
            invalid = Driver(directory, 'missing-host-address', invalid_cfg)
            try:
                code = invalid.proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                invalid.proc.kill()
                invalid.proc.wait()
                raise AssertionError('Missing host address did not cause startup failure')
            assert code != 0, invalid.output()
            RESULTS.append(dict(check='missing-host-address-fails', passed=True))
            monitor = rclpy.create_node('bundle_launch_monitor')
            try:
                for entry, algorithm in [('driver', None), ('view', None),
                                          ('fast_lio2', 'fast_lio'), ('calibration', 'lidar_imu_init')]:
                    launch_check(directory, monitor, entry, algorithm)
            finally:
                monitor.destroy_node()

    finally:
        rclpy.shutdown()
    print(json.dumps(dict(status='PASS', results=RESULTS), indent=2), flush=True)


if __name__ == '__main__':
    main()
