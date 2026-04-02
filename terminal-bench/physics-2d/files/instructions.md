# 2D Rigid Body Physics Engine

Implement a 2D rigid body physics engine in Python with oriented bounding box (OBB) collision detection, rotational dynamics, friction, configurable restitution, and iterative impulse resolution with accumulated clamping.

## CLI

```
python3 /app/files/physics2d.py --config <config.json> --output <output.jsonl> --steps <N>
```

## Config format

```json
{
  "width": 100.0,
  "height": 100.0,
  "dt": 0.01,
  "g": 9.81,
  "solver_iterations": 10,
  "bodies": [
    {
      "id": 0,
      "x": 10.0, "y": 50.0,
      "vx": 5.0, "vy": 0.0,
      "angle": 0.0, "omega": 0.0,
      "mass": 1.0,
      "w": 2.0, "h": 2.0,
      "e": 1.0, "mu": 0.0
    }
  ]
}
```

Bodies may be rectangles or circles. For rectangles, specify `w` and `h`. For circles, specify `"shape": "circle"` and `"r"` (radius).

```json
{
  "id": 1,
  "x": 50.0, "y": 50.0,
  "vx": 0.0, "vy": 0.0,
  "angle": 0.0, "omega": 0.0,
  "mass": 1.0,
  "shape": "circle", "r": 3.0,
  "e": 1.0, "mu": 0.0
}
```

Field defaults: `angle=0`, `omega=0`, `e=1`, `mu=0`, `solver_iterations=10`, `shape="rect"`.

## Output format

One JSON line per step:
```json
{"step": 0, "bodies": [{"id": 0, "x": 1.0, "y": 2.0, "vx": 0.5, "vy": -1.0, "angle": 0.1, "omega": 0.5}]}
```

All floats rounded to 6 decimal places. Bodies sorted by `id` ascending.

## Physics model

**Coordinates**: x increases right, y increases downward. Simulation bounds: x in [0, W], y in [0, H].

**Body properties**: position (x, y), velocity (vx, vy), angle theta (radians, counter-clockwise positive), angular velocity omega (rad/s, CCW positive), mass m, dimensions (w, h), coefficient of restitution e in [0, 1], friction coefficient mu >= 0.

**Moment of inertia**:
- Rectangle: `I = m * (w^2 + h^2) / 12`
- Circle: `I = m * r^2 / 2`

### Step algorithm (semi-implicit Euler)

For each timestep:

1. **Gravity**: for each body, `vy += g * dt`.
2. **Integrate**: for each body, `x += vx * dt`, `y += vy * dt`, `angle += omega * dt`.
3. **Body-body collisions**: detect all OBB overlaps using SAT. Resolve with iterative impulse solver using accumulated impulse clamping (see below).
4. **Body-body position correction**: push overlapping body pairs apart proportionally to inverse mass (see below).
5. **Wall collisions**: for each body, resolve penetrating vertices against all four walls.
6. **Record** output for this step.

### OBB vertices

Given center (cx, cy), half-extents hw = w/2, hh = h/2, and angle theta:

```
v0 = (cx + hw*cos(theta) + hh*sin(theta),  cy + hw*sin(theta) - hh*cos(theta))
v1 = (cx - hw*cos(theta) + hh*sin(theta),  cy - hw*sin(theta) - hh*cos(theta))
v2 = (cx - hw*cos(theta) - hh*sin(theta),  cy - hw*sin(theta) + hh*cos(theta))
v3 = (cx + hw*cos(theta) - hh*sin(theta),  cy + hw*sin(theta) + hh*cos(theta))
```

At angle=0: v0 = top-right, v1 = top-left, v2 = bottom-left, v3 = bottom-right (in y-down coords).

### SAT collision detection

For bodies A and B, test 4 potential separating axes --- 2 edge normals from each body:

- Body edge normals: `(cos(theta), sin(theta))` and `(-sin(theta), cos(theta))`

For each axis **a**: project all 8 vertices onto **a** (dot product). Compute intervals [minA, maxA] and [minB, maxB]. If `maxA < minB` or `maxB < minA` on any axis, the bodies do **not** collide.

If all 4 axes show overlap, the bodies collide. The axis with the **smallest** overlap magnitude is the **collision normal**.

**Orient** the collision normal **n** so that `n . (posA - posB) > 0` (points from B toward A). If the dot product is negative, negate n.

**Contact point**: compute the contact point P using support theory. For each body, find the support point along the collision normal: the support point of A is the mean position of A's vertex (or vertices, if tied) that is farthest in the direction from A toward B (i.e., minimum projection onto **n**). Similarly, the support point of B is the mean of B's vertex/vertices farthest toward A (maximum projection onto **n**). The contact point P is the midpoint of the two support points.

### Circle-circle collision detection

Two circles overlap when the distance between their centers is less than the sum of their radii. The collision normal points from circle B toward circle A. The overlap depth is `rA + rB - distance`. The contact point is the midpoint along the center-to-center line at the boundary: `P = posB + (rB / (rA + rB)) * (posA - posB)`. If the centers coincide (distance = 0), use normal `(1, 0)`.

### Circle-rectangle collision detection

To detect collision between a circle and a rotated rectangle (OBB):

1. Transform the circle's center into the rectangle's local coordinate frame by rotating by `-angle_rect` around the rectangle's center.
2. In local space, the rectangle is axis-aligned with half-extents `hw = w/2, hh = h/2`. Find the closest point on the AABB `[-hw, hw] x [-hh, hh]` to the local circle center by clamping.
3. Compute the distance from the local circle center to this closest point. If the distance is less than the circle's radius, there is a collision.
4. The overlap depth is `r - distance`. The collision normal is the direction from the closest point to the circle center (in local space), rotated back to world space, and oriented from the rect toward the circle (since the circle is "body A" from the rect's perspective — orient normal so it points from the non-circle body toward the circle).
5. If the circle center is inside the rectangle (distance = 0), find the axis of minimum penetration and use that as the separation direction.
6. The contact point is on the circle's surface at `circle_center - r * normal` (the point on the circle closest to the rect).

### Wall collisions for circles

For circles, wall penetration is computed directly from the center position and radius (no vertices needed). For each wall:
- Left wall: `pen = r - center.x`
- Right wall: `pen = center.x + r - W`
- Top wall: `pen = r - center.y`
- Bottom wall: `pen = center.y + r - H`

If pen > 0, the circle penetrates. The contact point is on the circle surface at `center - r * wall_normal`. Apply the same impulse and friction formulas as for rectangles. Position correction pushes the body out by the full penetration depth.

### Impulse resolution (body-body)

Given contact point P, collision normal **n** (pointing from B toward A), compute the contact velocity of each body at P. The contact velocity accounts for both linear velocity and the rotational contribution (omega cross r, where r is the vector from body center to P).

The **relative contact velocity** is `vRel = vA_contact - vB_contact`. The normal component is `vN = dot(vRel, n)`.

**Skip if vN >= 0** (bodies separating or resting).

**Velocity-dependent restitution**: if `|vN| < 1.0`, set `e_combined = 0.0` (prevents micro-bouncing at low relative velocities). Otherwise, `e_combined = sqrt(eA * eB)`.

**Normal impulse**: compute the scalar impulse magnitude `jN` such that applying `jN * n` to body A (and `-jN * n` to body B) at the contact point results in the post-collision normal relative velocity being `-e_combined * vN`. The effective mass in the denominator must account for both bodies' inverse masses and the rotational coupling through their moments of inertia (the angular contribution depends on the cross product of the lever arm with the normal direction).

The raw `jN` is then processed through accumulated impulse clamping (see below) before application.

**Friction impulse** (Coulomb model): after applying the clamped normal impulse, recompute the relative contact velocity with updated state. Extract the tangential component: `vT = vRel - dot(vRel, n) * n`. If `|vT| < 1e-10`, skip friction. The tangent direction is `t = vT / |vT|`.

Compute the friction impulse `jT` along the tangent direction using the same effective-mass formulation as for the normal impulse (but with the tangent direction instead of the normal). Combined friction: `mu_combined = sqrt(muA * muB)`.

The raw `jT` is then processed through accumulated friction clamping (see below).

### Iterative solver with accumulated impulse clamping

Use the sequential impulse method (Erin Catto, GDC 2006). At the start of each timestep, initialize a per-pair accumulator `(accN=0, accT=0)` for each body pair.

Repeat for `solver_iterations` times, processing body pairs `(idA < idB)` in ascending order:

1. Re-check overlap with SAT. If not overlapping, skip the pair but **preserve** its accumulator entry.
2. Compute contact point, normal, contact velocities, and vN.
3. If the pair has no accumulator yet, create one with zeros. If `vN >= 0`, skip.
4. Compute raw normal impulse `jN` (with velocity-dependent restitution).
5. **Accumulated clamping**: add `jN` to the normal accumulator. The accumulated normal impulse must remain non-negative (clamp to zero from below). Only apply the **change** (delta) in the accumulator to the bodies' velocities and angular velocities — not the raw `jN`.
6. Apply the normal impulse delta to both bodies (linear and angular velocities).
7. Recompute contact velocities with updated state. Compute tangent direction and raw friction impulse `jT`.
8. **Friction clamping**: add `jT` to the friction accumulator. Clamp the accumulated friction to `[-mu_combined * accN, mu_combined * accN]` using the **current** (post-clamp) normal accumulator. Apply only the delta.
9. Apply the friction impulse delta to both bodies.

### Body-body position correction

After the iterative solver completes, re-check all body pairs with SAT. For each overlapping pair, apply Baumgarte position correction: subtract a slop tolerance of 0.005 from the overlap depth (clamped to zero), multiply by a correction factor of 0.2, and distribute the resulting correction between the two bodies proportional to their inverse masses along the collision normal. The lighter body moves more.

### Wall collisions

Wall inward normals: left wall (x=0) has n=(1,0), right wall (x=W) has n=(-1,0), top wall (y=0) has n=(0,1), bottom wall (y=H) has n=(0,-1).

For each body, compute the 4 OBB vertices. Process walls in order: left, right, top, bottom.

For each wall: find the deepest penetrating vertex. Penetration is measured as the signed distance past the wall boundary (e.g., for the right wall: `vertex.x - W`; for the bottom wall: `vertex.y - H`). If multiple vertices tie for maximum penetration, average their positions to get the contact point. If no vertex penetrates (max pen <= 0), skip.

Apply an impulse at the contact point using the same formulas as body-body (but the wall has infinite mass, so only the body's inverse mass and inertia appear in the denominator). Use velocity-dependent restitution: if `|vN| < 1.0`, set `e = 0`; otherwise use the body's own restitution.

After the normal impulse, apply Coulomb friction at the contact point: compute the tangential component of the contact velocity, determine the friction impulse magnitude, and clamp it by `mu * |jN|` where `jN` is the normal impulse just applied.

Finally, correct the body's position by pushing it out of the wall by the full penetration depth along the wall normal.

## Self-verification

```
python3 -m pytest /app/files/tests.py -v
```

## Constraints

- Pure Python (stdlib + numpy allowed)
- Work offline. Do not modify test files.
