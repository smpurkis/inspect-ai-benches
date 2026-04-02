# N-Body Physics Simulator — Step 3: Barnes-Hut Tree

Replace the O(n²) brute-force pairwise computation with a Barnes-Hut octree for
O(n log n) performance. Target: 10× faster than brute-force on a 500-body seed.

## Barnes-Hut Algorithm

1. Build an octree over all body positions
2. For each body, traverse the tree. For each node:
   - If it's a leaf: compute force directly (pairwise)
   - If s/d < θ (θ=0.5): approximate with node's centre-of-mass
   - Otherwise: recurse into children
   where s = node size, d = distance from body to node centre of mass
3. θ = 0.5 (opening criterion)

## Correctness Requirements

- For seeds with ≤ 20 bodies: output must be **bitwise identical** to brute-force
  (Barnes-Hut is exact when tree has 1 body per leaf, and with θ=0.5 all small-N
   simulations should use direct computation for the few body pairs)
- For 500-body seed: approximation is acceptable (energy drift < 1e-2)
- All step 1 and step 2 tests must still pass

## Performance Target

Must complete 500-body / 1000-step simulation in < threshold_ms (see fixtures/timing_baseline.json)

## Building

```bash
cp /app/step_1/files/Cargo.toml /app/Cargo.toml
cp -r /app/step_1/files/src /app/src
cd /app && cargo build --release
```

## Verification

    python3 -m pytest /app/step_3/files/tests.py -v

## Constraints

- Work entirely offline inside the container.
- Keep outputs deterministic.
- Do not use `unsafe` blocks in sim.rs.
- Do not modify test or verifier files.
