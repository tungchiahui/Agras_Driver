#!/usr/bin/env python3
"""Verify a regular (non-symlink) driver install after moving its libraries.

Usage: source /opt/ros/humble/setup.bash
       python3 tools/tests/sdk_relocation_test.py /path/to/install/livox_ros_driver2
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile

from ament_index_python.packages import get_package_prefix


def runpath(binary):
    dynamic = subprocess.check_output(['readelf', '-d', str(binary)], text=True)
    match = re.search(r'\(RUNPATH\).*\[(.*?)\]', dynamic)
    assert match, dynamic
    return match.group(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prefix', type=Path)
    args = parser.parse_args()
    original = args.prefix.resolve()
    library = original / 'lib/liblivox_ros_driver2.so'
    assert not library.is_symlink(), 'Use an install built without --symlink-install'
    ros_prefix = Path(get_package_prefix('rclcpp'))

    with tempfile.TemporaryDirectory(prefix='agras-sdk-relocated-') as directory:
        root = Path(directory)
        relocated = root / 'relocated'
        shutil.copytree(original / 'lib', relocated / 'lib')
        sdk = relocated / 'lib/libagras_livox_lidar_sdk_shared.so'
        executable = relocated / 'lib/livox_ros_driver2/livox_ros_driver2_node'
        assert runpath(relocated / 'lib/liblivox_ros_driver2.so') == '$ORIGIN'
        assert runpath(executable) == '$ORIGIN/..'

        cfg = json.loads((original / 'share/livox_ros_driver2/config/AGRAS_MID360_config.json').read_text())
        for key in ('cmd_data_ip', 'push_msg_ip', 'point_data_ip', 'imu_data_ip'):
            cfg['MID360']['host_net_info'][key] = '127.0.0.1'
        cfg['lidar_configs'][0]['ip'] = '127.0.0.2'
        config = root / 'network.json'
        config.write_text(json.dumps(cfg))
        legacy = root / 'legacy'
        legacy.mkdir()
        (legacy / 'liblivox_lidar_sdk_shared.so').write_text('not the Agras SDK\n')
        # No workspace or relocated package appears in the library search path.
        env = dict(os.environ, AMENT_PREFIX_PATH=str(ros_prefix),
                   LD_LIBRARY_PATH=f'{legacy}:/usr/local/lib:{ros_prefix / "lib"}',
                   ROS_LOCALHOST_ONLY='1', ROS_DOMAIN_ID='88')
        env.pop('LD_PRELOAD', None)
        with tempfile.TemporaryFile(mode='w+') as log:
            proc = subprocess.Popen([str(executable), '--ros-args', '-p',
                                     'user_config_path:=' + str(config)],
                                    cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                try:
                    proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    pass
                log.seek(0)
                output = log.read()
                assert proc.poll() is None, output
                assert 'Agras SDK library: ' + str(sdk) in output, output
                assert 'Agras SDK version: ' in output, output
                maps = Path(f'/proc/{proc.pid}/maps').read_text()
                assert str(sdk) in maps, maps
                assert str(original) not in maps, maps
                assert 'liblivox_lidar_sdk_shared.so' not in maps, maps
                proc.send_signal(signal.SIGINT)
                assert proc.wait(timeout=8) == 0
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
    print(json.dumps(dict(status='PASS', check='sdk-relocation',
                         runpath_library='$ORIGIN', runpath_node='$ORIGIN/..',
                         legacy_sdk_shadow_ignored=True, clean_shutdown=True)))


if __name__ == '__main__':
    main()
