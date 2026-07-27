#!/usr/bin/env bash
# Slow, lush, infinite bonsai. Slower step time, longer life (more leaves),
# longer pause between regrows so the finished tree is visible.
exec cbonsai \
  --live \
  --infinite \
  --time=0.18 \
  --wait=30 \
  --life=38 \
  --multiplier=5
