
if [ -f ./config.local.sh ]; then
    source ./config.local.sh
else
    source ../chapter_03_load_monitoring_teleop/config.sh
fi

uv run python ./sim_leader_teleop.py \
    --port="$TELEOP_PORT" \
    --id="$TELEOP_ID"
