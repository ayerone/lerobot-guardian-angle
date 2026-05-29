
if [ -f ./config.local.sh ]; then
    source ./config.local.sh
else
    source ./config.sh
fi

uv run python ./teleop_check_motors.py \
    --robot.type=so101_follower \
    --robot.port="$ROBOT_PORT" \
    --robot.id="$ROBOT_ID" \
    --robot.cameras='{"wrist_cam": {"type": "opencv", "index_or_path": 0, "width": 640, "height": 480, "fps": 30}}' \
    --teleop.type=so101_leader \
    --teleop.port="$TELEOP_PORT" \
    --teleop.id="$TELEOP_ID" \
    --display_data=true \
    --log_motor_current=true \
    --log_motor_temperature=true \
    --log_motor_load=true
