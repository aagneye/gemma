#!/usr/bin/env bash
# Supervisor for daily_ship.py: restarts it if it exits. Started in tmux session `dailyship`; a cron watchdog line
# (installed by install_dailyship_cron.sh) recreates the tmux session after a crash or a VM reboot.
R=/mnt/biohub/kdata/gemma4; cd $R; source $R/.venv/bin/activate
while true; do
  python ~/gemma4_vm/daily_ship.py >> $R/logs/daily_ship.stdout 2>&1
  echo "$(date -u) daily_ship.py exited; restarting in 60 s" >> $R/logs/daily_ship.log
  sleep 60
done
