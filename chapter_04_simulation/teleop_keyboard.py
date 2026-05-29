"""
Local override of KeyboardEndEffectorTeleop with bug fixes not yet upstreamed.

Fixes over the lerobot library version:
  - _on_press/_on_release handle special keys (arrow, shift, ctrl) as Key objects;
    the parent class silently dropped them because it only queued keys with a char.
  - connect() uses suppress=True so key events are not replayed in the terminal
    after the script exits.
  - get_action() no longer clears current_pressed every frame, which was breaking
    continuous movement for keys that don't auto-repeat (shift, ctrl).
  - get_action() skips stale released-key entries (val=False) so they cannot
    overwrite a simultaneously pressed key during dict iteration.
  - Arrow key mapping: Up=X+, Down=X-, Left=Y+, Right=Y-.
  - _should_disconnect flag makes is_connected return False immediately when ESC
    is pressed, rather than waiting for the listener thread to fully exit.
"""

import logging
import os
import sys
from queue import Queue
from typing import Any

from lerobot.teleoperators.keyboard.configuration_keyboard import KeyboardEndEffectorTeleopConfig
from lerobot.teleoperators.keyboard.teleop_keyboard import KeyboardTeleop
from lerobot.teleoperators.utils import TeleopEvents
from lerobot.utils.decorators import check_if_already_connected, check_if_not_connected
from lerobot.utils.import_utils import _pynput_available

PYNPUT_AVAILABLE = _pynput_available
keyboard = None
if PYNPUT_AVAILABLE:
    try:
        if ("DISPLAY" not in os.environ) and ("linux" in sys.platform):
            PYNPUT_AVAILABLE = False
        else:
            from pynput import keyboard
    except Exception as e:
        PYNPUT_AVAILABLE = False
        logging.info(f"Could not import pynput: {e}")


class KeyboardEndEffectorTeleop(KeyboardTeleop):
    """
    Fixed keyboard end-effector teleop for use with SO-101 and RobotKinematics.
    Inherits connection/state management from KeyboardTeleop; overrides key
    handling and get_action to work correctly with special keys on Linux/Wayland.
    """

    name = "keyboard_ee"

    def __init__(self, config: KeyboardEndEffectorTeleopConfig):
        super().__init__(config)
        self.config = config
        self.misc_keys_queue = Queue()
        self._should_disconnect = False

    @property
    def is_connected(self) -> bool:
        if self._should_disconnect:
            return False
        return super().is_connected

    def _on_press(self, key):
        if hasattr(key, "char") and key.char is not None:
            self.event_queue.put((key.char, True))
        else:
            self.event_queue.put((key, True))

    def _on_release(self, key):
        if hasattr(key, "char") and key.char is not None:
            self.event_queue.put((key.char, False))
        else:
            self.event_queue.put((key, False))
        if key == keyboard.Key.esc:
            logging.info("ESC pressed, disconnecting.")
            self.disconnect()
            self._should_disconnect = True

    @check_if_already_connected
    def connect(self) -> None:
        if PYNPUT_AVAILABLE:
            self.listener = keyboard.Listener(
                on_press=self._on_press,
                on_release=self._on_release,
                suppress=True,
            )
            self.listener.start()
        else:
            logging.info("pynput not available - skipping local keyboard listener.")
            self.listener = None

    @property
    def action_features(self) -> dict:
        if self.config.use_gripper:
            return {
                "dtype": "float32",
                "shape": (4,),
                "names": {"delta_x": 0, "delta_y": 1, "delta_z": 2, "gripper": 3},
            }
        else:
            return {
                "dtype": "float32",
                "shape": (3,),
                "names": {"delta_x": 0, "delta_y": 1, "delta_z": 2},
            }

    @check_if_not_connected
    def get_action(self) -> dict:
        self._drain_pressed_keys()
        delta_x = 0.0
        delta_y = 0.0
        delta_z = 0.0
        gripper_action = 1.0

        for key, val in self.current_pressed.items():
            if not val:
                continue
            if key == keyboard.Key.up:
                delta_x = 1
            elif key == keyboard.Key.down:
                delta_x = -1
            elif key == keyboard.Key.left:
                delta_y = 1
            elif key == keyboard.Key.right:
                delta_y = -1
            elif key == keyboard.Key.shift:
                delta_z = -1
            elif key == keyboard.Key.shift_r:
                delta_z = 1
            elif key == keyboard.Key.ctrl_r:
                gripper_action = 2
            elif key == keyboard.Key.ctrl_l:
                gripper_action = 0
            else:
                self.misc_keys_queue.put(key)

        action_dict = {
            "delta_x": delta_x,
            "delta_y": delta_y,
            "delta_z": delta_z,
        }
        if self.config.use_gripper:
            action_dict["gripper"] = gripper_action

        return action_dict

    def get_teleop_events(self) -> dict[str, Any]:
        if not self.is_connected:
            return {
                TeleopEvents.IS_INTERVENTION: False,
                TeleopEvents.TERMINATE_EPISODE: False,
                TeleopEvents.SUCCESS: False,
                TeleopEvents.RERECORD_EPISODE: False,
            }

        movement_keys = [
            keyboard.Key.up,
            keyboard.Key.down,
            keyboard.Key.left,
            keyboard.Key.right,
            keyboard.Key.shift,
            keyboard.Key.shift_r,
            keyboard.Key.ctrl_r,
            keyboard.Key.ctrl_l,
        ]
        is_intervention = any(self.current_pressed.get(key, False) for key in movement_keys)

        terminate_episode = False
        success = False
        rerecord_episode = False

        while not self.misc_keys_queue.empty():
            key = self.misc_keys_queue.get_nowait()
            if key == "s":
                success = True
            elif key == "r":
                terminate_episode = True
                rerecord_episode = True
            elif key == "q":
                terminate_episode = True
                success = False

        return {
            TeleopEvents.IS_INTERVENTION: is_intervention,
            TeleopEvents.TERMINATE_EPISODE: terminate_episode,
            TeleopEvents.SUCCESS: success,
            TeleopEvents.RERECORD_EPISODE: rerecord_episode,
        }
