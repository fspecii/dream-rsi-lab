# Replay a real recorded discovery without a model

These three worlds and the learned controller were collected with the local
`qwen3.5:0.8b` model in `runs/qwen08-focused-v2`. They are real measured traces,
not the scripted fixtures in the test suite.

From the repository root:

```bash
python3 -m dream_rsi replay --world examples/recorded-world.json \
  --policy examples/fixed-policy.json --budget 16 \
  --history examples/earlier-world-0.json examples/earlier-world-1.json

python3 -m dream_rsi replay --world examples/recorded-world.json \
  --policy examples/learned-policy.json --budget 16 \
  --history examples/earlier-world-0.json examples/earlier-world-1.json
```

Expected: both replay trajectories reach score **1.0**. Fixed exploration reveals
**16** recorded attempts over **8** rounds. The learned controller reveals **4**
attempts over **2** rounds. Both earlier worlds supply the completed-history
context needed by the controller's conditional grid-planning code.

Inspect the original larger tree with:

```bash
python3 -m dream_rsi inspect examples/recorded-world.json
```

This offline example demonstrates how replay works. It does not by itself prove
generalization: [the experiment notes](../docs/experiments.md) distinguish replay
from independently collected fresh episodes. The score of 1.0 is attainable with
simple arithmetic progressions and is not a new mathematical record.
