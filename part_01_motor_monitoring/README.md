# Part 01 — Motor Monitoring

**Goal:** Monitor stress on the servo in real time. We'll use the shoulder pan servo as an example and display the motor's position, load, current, and temperature while the arm is stationary and moving.

---

## The question

Are there any warning signs that we can use to avoid damaging our robot's motors?

The LeRobot code that operates the SO-101 reads and writes positions to the motors, so what other information can we get from them that will help us solve this problem?

The Feetech STS3215 servos expose several feedback registers. Two stood out: `Present_Load` and `Present_Current`, so I started there.

**Present_Load and Present_Current**

`Present_Load` is the PWM duty cycle of the control output driving the motor. It is a signed value, corresponding to clockwise versus counterclockwise torque. ([STS e-manual, section 2.4](http://doc.feetech.cn/#/prodinfodownload?srcType=FT-SMS-STS-emanual-229f4476422d4059abfb1cb0))

`Present_Current` is the magnitude of the actual measured motor current (it's always non-negative).

## Building the live plot

I did this development in a Jupyter Notebook using [Datalayer's JupyterLab MCP server](https://github.com/datalayer/jupyter-mcp-server). The notebook reads the `Present_Position`, `Present_Load`, `Present_Current`, and `Present_Temperature` registers from the Feetech servo bus and updates a live plot using ipympl's `%matplotlib widget`.

The plot runs in a background thread because of a JupyterLab constraint: while a cell is executing (kernel is "busy"), all widget updates are held and delivered only when the cell finishes. A blocking read loop inside a cell gives you nothing until you interrupt it. The fix is to have each cell return immediately — start the work in a daemon thread, let the cell finish, let the kernel go idle, and then updates flow to the browser continuously.

With a second thread running the robot movement, you need a `threading.Lock` around every serial bus access. I learned this the hard way (more about this in [Part 02 — Safe Movements](../part_02_safe_movements/)).

## Experiment

I programmed the arm to sweep back and forth between -30° and +30° on the shoulder pan joint, pausing for 1.5 seconds at each extreme. At various points I applied resistance with my hand to see how much the load and current would increase in response.

## What the data showed

With the four-panel live plot running while the arm swept ±30° back and forth, a few things became clear:

**Resisting movement by hand increased both load and current, as expected.** The more resistance applied, the higher both values climbed.

**Load stays elevated after movement stops.** Even on the shoulder_pan joint, which rotates about a vertical axis and has essentially no gravitational load, Present_Load remains nonzero after the arm stops moving, presumably from the PID fighting stiction (static friction) in the high reduction ratio gearbox.

**Empirical calibration: ~6 mA per count.** I measured total system current with a DC ammeter while observing Present_Current in the notebook. At peak hand resistance the motor was drawing an additional 550 mA, while Present_Current was at 90 counts — giving roughly 6 mA/count.

## Where this leads

This part established which values to read from the motors and how to read them. The next question is: what does the data look like under normal operating conditions — during teleoperation, dataset recording, and policy rollout?

The next step is integrating these readings into `lerobot-teleoperate` or `lerobot-record` to monitor motor stress during actual operation. One challenge will be keeping the timing loop tight while adding extra bus reads. `Present_Load` or `Present_Current` could be sampled frequently as a real-time stress indicator, or `Present_Temperature` could be sampled every second or so and still potentially provide an early warning before damage occurs.

## Notebook

[motor_currents.ipynb](motor_currents.ipynb)
