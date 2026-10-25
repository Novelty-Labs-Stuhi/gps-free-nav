#!/bin/bash
cd /Users/arseniichistiakov/stuhi-hack
SSH="ssh -o StrictHostKeyChecking=no -o ConnectTimeout=20 -i $HOME/.ssh/google_compute_engine"
H=arseniichistiakov@136.66.238.250
for i in $(seq 1 200); do
  for pair in "flat:flat" "flat_ekf:flat_ekf"; do
    remote=${pair%%:*}; local=data/${pair##*:}; mkdir -p $local
    rsync -az -e "$SSH" --include='*.json' --exclude='*' $H:~/$remote/ $local/ 2>/dev/null
    rsync -az -e "$SSH" $H:~/$remote.log $local/flat.log 2>/dev/null
    n=$(ls $local/*.json 2>/dev/null | grep -v rows.json | wc -l | tr -d ' ')
    echo "$(date +%H:%M) $local worlds done: $n"
    [ "$n" -gt 0 ] && FLAT_DIR=$local uv run --with matplotlib python "$1" $local/progress.png 2>&1 | tail -1
    for f in $local/*.json; do
      w=$(basename $f .json); [ "$w" = rows ] && continue
      [ -f $local/${w}_best_run.png ] || FLAT_DIR=$local uv run --with matplotlib python "$2" $w 2>&1 | tail -1
    done
  done
  grep -q "=== FINAL" data/flat_ekf/flat.log 2>/dev/null && break
  sleep 120
done
echo SYNC-LOOP-END
