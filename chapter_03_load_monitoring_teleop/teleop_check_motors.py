"""
Teleoperate an SO-101 follower arm with optional Rerun logging of motor current,
temperature, and load for all motors.

Usage:
    uv run python ./teleop_check_motors.py \
        --robot.type=so101_follower \
        --robot.port=/dev/serial/by-id/usb-1a86_USB_Single_Serial_5AAF263835-if00 \
        --robot.id=my_so101_follower \
        --robot.cameras='{"wrist_cam": {"type": "opencv", "index_or_path": 0, "width": 640, "height": 480, "fps": 30}}' \
        --teleop.type=so101_leader \
        --teleop.port=/dev/serial/by-id/usb-1a86_USB_Single_Serial_5AA9024519-if00 \
        --teleop.id=aaron_default_leader \
        --display_data=true \
        --log_motor_current=true \
        --log_motor_temperature=true \
        --log_motor_load=true
"""

import logging
import time
from dataclasses import asdict, dataclass
from pprint import pformat

from lerobot.cameras.opencv import OpenCVCameraConfig  # noqa: F401
from lerobot.cameras.realsense import RealSenseCameraConfig  # noqa: F401
from lerobot.cameras.zmq import ZMQCameraConfig  # noqa: F401
from lerobot.configs import parser
from lerobot.processor import (
    RobotAction,
    RobotObservation,
    RobotProcessorPipeline,
    make_default_processors,
)
from lerobot.robots import (  # noqa: F401
    Robot,
    RobotConfig,
    make_robot_from_config,
    so_follower,
)
from lerobot.teleoperators import (  # noqa: F401
    Teleoperator,
    TeleoperatorConfig,
    keyboard,
    make_teleoperator_from_config,
    so_leader,
)
from lerobot.utils.import_utils import register_third_party_plugins
from lerobot.utils.robot_utils import precise_sleep
from lerobot.utils.utils import init_logging, move_cursor_up
from lerobot.utils.visualization_utils import init_rerun, log_rerun_data, shutdown_rerun


@dataclass
class TeleoperateConfig:
    teleop: TeleoperatorConfig
    robot: RobotConfig
    fps: int = 60
    teleop_time_s: float | None = None
    display_data: bool = False
    display_ip: str | None = None
    display_port: int | None = None
    display_compressed_images: bool = False
    log_motor_current: bool = False
    log_motor_temperature: bool = False
    log_motor_load: bool = False


def teleop_loop(
    teleop: Teleoperator,
    robot: Robot,
    fps: int,
    teleop_action_processor: RobotProcessorPipeline[tuple[RobotAction, RobotObservation], RobotAction],
    robot_action_processor: RobotProcessorPipeline[tuple[RobotAction, RobotObservation], RobotAction],
    robot_observation_processor: RobotProcessorPipeline[RobotObservation, RobotObservation],
    log_motor_current: bool,
    log_motor_temperature: bool,
    log_motor_load: bool,
    display_data: bool = False,
    duration: float | None = None,
    display_compressed_images: bool = False,
):
    display_len = max(len(key) for key in robot.action_features)
    start = time.perf_counter()

    _alpha = 0.1
    _ema = [0.0] * 9  # one slot per timed segment

    def ms(t0: float, t1: float) -> float:
        return (t1 - t0) * 1e3

    while True:
        t0 = time.perf_counter()

        obs = robot.get_observation()
        t1 = time.perf_counter()

        raw_action = teleop.get_action()
        t2 = time.perf_counter()

        teleop_action = teleop_action_processor((raw_action, obs))
        robot_action_to_send = robot_action_processor((teleop_action, obs))
        t3 = time.perf_counter()

        _ = robot.send_action(robot_action_to_send)
        t4 = time.perf_counter()

        t5 = t4
        t6 = t4
        t7 = t4
        if display_data:
            import rerun as rr

            obs_transition = robot_observation_processor(obs)
            log_rerun_data(
                observation=obs_transition,
                action=teleop_action,
                compress_images=display_compressed_images,
            )
            t5 = time.perf_counter()

            if log_motor_current:
                currents = robot.bus.sync_read("Present_Current")
                for motor, value in currents.items():
                    rr.log(f"motor_current/{motor}", rr.Scalars(float(value)))
            t6 = time.perf_counter()

            if log_motor_temperature:
                temps = robot.bus.sync_read("Present_Temperature")
                for motor, value in temps.items():
                    rr.log(f"motor_temperature/{motor}", rr.Scalars(float(value)))
            t7 = time.perf_counter()

            if log_motor_load:
                loads = robot.bus.sync_read("Present_Load")
                for motor, value in loads.items():
                    rr.log(f"motor_load/{motor}", rr.Scalars(float(value)))

            print("\n" + "-" * (display_len + 10))
            print(f"{'NAME':<{display_len}} | {'NORM':>7}")
            for motor, value in robot_action_to_send.items():
                print(f"{motor:<{display_len}} | {value:>7.2f}")
            move_cursor_up(len(robot_action_to_send) + 3)

        t8 = time.perf_counter()
        precise_sleep(max(1 / fps - (t8 - t0), 0.0))
        t9 = time.perf_counter()

        raw = [ms(t0,t1), ms(t1,t2), ms(t2,t3), ms(t3,t4), ms(t4,t5), ms(t5,t6), ms(t6,t7), ms(t7,t8), ms(t8,t9)]
        _ema[:] = [_alpha * r + (1 - _alpha) * e for r, e in zip(raw, _ema)]
        e = [int(v) for v in _ema]
        total = int(sum(_ema))
        print(
            f"obs:{e[0]:2d} teleop:{e[1]:2d} proc:{e[2]:2d}"
            f" send:{e[3]:2d} disp:{e[4]:2d}"
            f" current:{e[5]:2d} temp:{e[6]:2d} load:{e[7]:2d}"
            f" sleep:{e[8]:2d} | total:{total:2d}ms"
        )
        move_cursor_up(1)

        if duration is not None and time.perf_counter() - start >= duration:
            return


@parser.wrap()
def teleoperate(cfg: TeleoperateConfig):
    init_logging()
    logging.info(pformat(asdict(cfg)))
    if cfg.display_data:
        init_rerun(session_name="teleoperation", ip=cfg.display_ip, port=cfg.display_port)
    display_compressed_images = (
        True
        if (cfg.display_data and cfg.display_ip is not None and cfg.display_port is not None)
        else cfg.display_compressed_images
    )

    teleop = make_teleoperator_from_config(cfg.teleop)
    robot = make_robot_from_config(cfg.robot)
    teleop_action_processor, robot_action_processor, robot_observation_processor = make_default_processors()

    teleop.connect()
    robot.connect()

    try:
        teleop_loop(
            teleop=teleop,
            robot=robot,
            fps=cfg.fps,
            display_data=cfg.display_data,
            duration=cfg.teleop_time_s,
            teleop_action_processor=teleop_action_processor,
            robot_action_processor=robot_action_processor,
            robot_observation_processor=robot_observation_processor,
            display_compressed_images=display_compressed_images,
            log_motor_current=cfg.log_motor_current,
            log_motor_temperature=cfg.log_motor_temperature,
            log_motor_load=cfg.log_motor_load,
        )
    except KeyboardInterrupt:
        pass
    finally:
        if cfg.display_data:
            shutdown_rerun()
        teleop.disconnect()
        robot.disconnect()


if __name__ == "__main__":
    register_third_party_plugins()
    teleoperate()
