#!/usr/bin/env bash
# Install (idempotently) the cron watchdog that keeps the `dailyship` tmux session alive, and (re)start it now.
# Only lines containing "dailyship" are replaced; other crontab entries of this user are preserved.
LINE='*/20 * * * * tmux has-session -t =dailyship 2>/dev/null || tmux new-session -d -s dailyship "bash /home/azureuser/gemma4_vm/dailyship_loop.sh"'
( crontab -l 2>/dev/null | grep -v dailyship; echo "$LINE" ) | crontab -
tmux kill-session -t dailyship 2>/dev/null
tmux new-session -d -s dailyship "bash /home/azureuser/gemma4_vm/dailyship_loop.sh"
sleep 3; tmux has-session -t dailyship && echo "dailyship running"; crontab -l | grep -c dailyship
