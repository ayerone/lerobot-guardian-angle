# Chapter 03 — Load Monitoring During Teleoperation

## What This Test Checks

You can run this health check on your SO-101 arm to make sure there is no problem with the motors. You can turn on recording for Present_Load, Present_Current, and Present_Temperature (see [chapter_01_motor_monitoring](../chapter_01_motor_monitoring/README.md)), teleoperate the robot normally, and observe these quantities in Rerun.

Catching errors caused by bad calibration, degrading motors, and dangerous operating habits can avoid robot downtime.

## Prerequisites

- SO-101 leader and follower arms connected and calibrated
- The Rerun extra installed (`pip install 'lerobot[viz]'`)

## Running the Test

From the `chapter_03_load_monitoring_teleop/` directory:

```bash
bash run_teleop.sh
```

This starts teleoperation with all three motor signals logging to Rerun. Test various movements to see what motor loads and currents this produces.

## What I Saw

Load and current are responsive to motor movements, and respond as you would expect to movements with and against gravity.

As expected, resisting the robot's movements causes load and current to increase.

At rest, load settles at a low level and current drops to single digits, even under gravity.

Slow movements do not spike current or load.

Temperature rises very slowly while exercising the robot. The graphs do display very high spikes (50°C+) which appear to be false readings.
