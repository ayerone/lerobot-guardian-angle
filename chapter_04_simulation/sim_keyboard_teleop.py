#!/usr/bin/env python
"""
Keyboard end-effector teleoperation of the SO-101 in MuJoCo simulation.

Same keyboard controls as the real-robot teleop script; no hardware required.

Run from the repo root:
  uv run python experiments/simulation/sim_keyboard_teleop.py

v01 — initial version:
  - Loads SO-101 MuJoCo scene and URDF; uses placo RobotKinematics for FK/IK.
  - Arrow keys / shift / ctrl map to XYZ EE deltas and gripper open/close.
  - Velocity ramping over RAMP_FRAMES for smooth motion.
  - Hard bounding-box workspace limits (EE_BOUNDS_MIN / EE_BOUNDS_MAX).
  - Home pose set to [0, -60, 60, 30, 0, 50] deg to avoid near-singular default.
"""

import os
import sys
import time

# Force GLFW to use X11 instead of Wayland so the compositor's display scale
# factor is not applied to the viewer window.
# os.environ.pop("WAYLAND_DISPLAY", None) # didn't work

import mujoco
import mujoco.viewer
import numpy as np

from teleop_keyboard import KeyboardEndEffectorTeleop, KeyboardEndEffectorTeleopConfig

from lerobot.model.kinematics import RobotKinematics
from lerobot.utils.robot_utils import precise_sleep

# ── Configuration ─────────────────────────────────────────────────────────────

MJCF_PATH  = "./SO101/scene.xml"
URDF_PATH  = "./SO101/so101_new_calib.urdf"
TARGET_FRAME = "gripper_frame_link"

FPS          = 30
STEP_M       = 0.005
GRIPPER_SPEED = 3.0
RAMP_FRAMES  = 6

EE_BOUNDS_MIN = np.array([-0.50, -0.50,  0.00])
EE_BOUNDS_MAX = np.array([ 0.50,  0.50,  0.60])

MOTOR_NAMES = ["shoulder_pan", "shoulder_lift", "elbow_flex",
               "wrist_flex", "wrist_roll", "gripper"]

# Starting joint angles in degrees. The all-zero MJCF default puts the arm in a
# near-singular configuration; this home pose gives IK a well-conditioned region
# to work from. Tune these to match a comfortable real-robot ready position.
HOME_Q_DEG = np.array([0.0, -60.0, 60.0, 30.0, 0.0, 50.0])

# ─────────────────────────────────────────────────────────────────────────────


def main():
    model = mujoco.MjModel.from_xml_path(MJCF_PATH)
    data  = mujoco.MjData(model)

    # Index into qpos / ctrl for each named joint / actuator.
    # Cast to int: qposadr can be a 1-element numpy array, which causes fancy
    # indexing and makes data.qpos[i] return an array instead of a scalar.
    qpos_ids = [int(model.joint(name).qposadr) for name in MOTOR_NAMES]
    ctrl_ids = [int(model.actuator(name).id)   for name in MOTOR_NAMES]

    def get_q_deg():
        """Read current joint positions from sim state, in degrees."""
        return np.degrees(np.array([data.qpos[i] for i in qpos_ids]))

    def set_ctrl_deg(q_deg):
        """Write joint targets (degrees) to MuJoCo actuators (radians)."""
        for ctrl_id, deg in zip(ctrl_ids, q_deg):
            data.ctrl[ctrl_id] = np.radians(deg)

    kinematics = RobotKinematics(
        urdf_path=URDF_PATH,
        target_frame_name=TARGET_FRAME,
        joint_names=MOTOR_NAMES,
    )

    teleop = KeyboardEndEffectorTeleop(KeyboardEndEffectorTeleopConfig())
    teleop.connect()

    print("\nKeyboard EE teleop (simulation) ready.")
    print(f"  {'Key':<14} Action")
    print(f"  {'-'*14} ------")
    print(f"  {'Up':<14} X+")
    print(f"  {'Down':<14} X−")
    print(f"  {'Left':<14} Y+")
    print(f"  {'Right':<14} Y−")
    print(f"  {'Left Shift':<14} Z−")
    print(f"  {'Right Shift':<14} Z+")
    print(f"  {'Left Ctrl':<14} Close gripper")
    print(f"  {'Right Ctrl':<14} Open gripper")
    print(f"  {'ESC':<14} Quit")
    print()

    # Set simulation to home pose and let physics settle before the control loop.
    for i, (qpos_id, ctrl_id) in enumerate(zip(qpos_ids, ctrl_ids)):
        data.qpos[qpos_id] = np.radians(HOME_Q_DEG[i])
        data.ctrl[ctrl_id] = np.radians(HOME_Q_DEG[i])
    mujoco.mj_forward(model, data)

    q = get_q_deg()
    T_desired = kinematics.forward_kinematics(q)
    q_target  = q.copy()
    vel       = np.zeros(3)
    accel     = STEP_M / RAMP_FRAMES
    gripper_pos = q[MOTOR_NAMES.index("gripper")]  # degrees

    # Number of physics steps per control frame so sim time matches wall time.
    n_substeps = max(1, round(1.0 / (FPS * model.opt.timestep)))

    with mujoco.viewer.launch_passive(model, data, show_left_ui=False, show_right_ui=False) as viewer:
        while viewer.is_running() and teleop.is_connected:
            t0 = time.perf_counter()

            q = get_q_deg()

            kb = teleop.get_action()
            target_vel = np.array([kb["delta_x"], kb["delta_y"], kb["delta_z"]]) * STEP_M
            vel += np.clip(target_vel - vel, -accel, accel)

            if np.any(vel != 0.0):
                T_desired[0, 3] += vel[0]
                T_desired[1, 3] += vel[1]
                T_desired[2, 3] += vel[2]
                T_desired[:3, 3] = np.clip(T_desired[:3, 3], EE_BOUNDS_MIN, EE_BOUNDS_MAX)
                q_target = kinematics.inverse_kinematics(q_target, T_desired)

            # Gripper: integrate on degree scale, then convert to radians for MuJoCo.
            gripper_pos = float(
                np.clip(gripper_pos + (kb["gripper"] - 1) * GRIPPER_SPEED, 0.0, 100.0)
            )

            x, y, z = T_desired[:3, 3]
            print(f"\r  EE  x={x:+.2f}  y={y:+.2f}  z={z:+.2f} m", end="", flush=True)

            # Send arm joints from IK; gripper separately.
            arm_q = {name: q_target[i]
                     for i, name in enumerate(MOTOR_NAMES) if name != "gripper"}
            for i, name in enumerate(MOTOR_NAMES):
                if name == "gripper":
                    data.ctrl[ctrl_ids[i]] = np.radians(gripper_pos)
                else:
                    data.ctrl[ctrl_ids[i]] = np.radians(q_target[i])

            for _ in range(n_substeps):
                mujoco.mj_step(model, data)
            viewer.sync()

            precise_sleep(max(1.0 / FPS - (time.perf_counter() - t0), 0.0))

        viewer.close()

    if teleop.is_connected:
        teleop.disconnect()


if __name__ == "__main__":
    main()
