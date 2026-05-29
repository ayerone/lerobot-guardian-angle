#!/usr/bin/env python
"""
SO-101 leader → MuJoCo simulated follower teleoperation.

The physical leader arm's joint angles are read each frame and applied
directly to the simulated arm — no IK required since leader and follower
share the same kinematics.

Run from the chapter_04_simulation/ directory:
  bash run_sim_leader_teleop.sh
  # or directly:
  uv run python ./sim_leader_teleop.py \
      --port=/dev/serial/by-id/... \
      --id=my_leader_id
"""

import argparse
import time

import mujoco
import mujoco.viewer
import numpy as np

from lerobot.teleoperators.so_leader import SO101LeaderConfig
from lerobot.teleoperators import make_teleoperator_from_config
from lerobot.utils.robot_utils import precise_sleep

# ── Configuration ──────────────────────────────────────────────────────────────

MJCF_PATH = "./SO101/scene.xml"

FPS = 30

MOTOR_NAMES = ["shoulder_pan", "shoulder_lift", "elbow_flex",
               "wrist_flex", "wrist_roll", "gripper"]

HOME_Q_DEG = np.array([0.0, -60.0, 60.0, 30.0, 0.0, 50.0])

# ──────────────────────────────────────────────────────────────────────────────


def main(port: str, leader_id: str) -> None:
    model = mujoco.MjModel.from_xml_path(MJCF_PATH)
    data = mujoco.MjData(model)

    qpos_ids = [int(model.joint(name).qposadr) for name in MOTOR_NAMES]
    ctrl_ids = [int(model.actuator(name).id) for name in MOTOR_NAMES]

    # Set home pose
    for i, (qp, ci) in enumerate(zip(qpos_ids, ctrl_ids)):
        data.qpos[qp] = np.radians(HOME_Q_DEG[i])
        data.ctrl[ci] = np.radians(HOME_Q_DEG[i])
    mujoco.mj_forward(model, data)

    n_substeps = max(1, round(1.0 / (FPS * model.opt.timestep)))

    cfg = SO101LeaderConfig(port=port, id=leader_id)
    teleop = make_teleoperator_from_config(cfg)
    teleop.connect()

    print("\nSO-101 leader → sim ready. Move the leader arm to control the simulation.")
    print("Close the MuJoCo viewer window to quit.\n")

    with mujoco.viewer.launch_passive(
        model, data, show_left_ui=False, show_right_ui=False
    ) as viewer:
        while viewer.is_running():
            t0 = time.perf_counter()

            action = teleop.get_action()

            for name in MOTOR_NAMES:
                key = f"{name}.pos"
                if key in action:
                    idx = MOTOR_NAMES.index(name)
                    data.ctrl[ctrl_ids[idx]] = np.radians(action[key])

            for _ in range(n_substeps):
                mujoco.mj_step(model, data)
            viewer.sync()

            precise_sleep(max(1.0 / FPS - (time.perf_counter() - t0), 0.0))

        viewer.close()

    teleop.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, help="Leader serial port")
    parser.add_argument("--id", required=True, help="Leader calibration ID")
    args = parser.parse_args()
    main(port=args.port, leader_id=args.id)
