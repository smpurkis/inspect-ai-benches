use crate::types::*;

/// Compute gravitational accelerations for all bodies.
pub fn compute_accelerations(bodies: &[Body], g: f64) -> Vec<[f64; 3]> {
    let n = bodies.len();
    let mut accel = vec![[0.0f64; 3]; n];

    for i in 0..n {
        for j in 0..n {
            if i == j {
                continue;
            }

            let dx = bodies[j].position[0] - bodies[i].position[0];
            let dy = bodies[j].position[1] - bodies[i].position[1];
            let dz = bodies[j].position[2] - bodies[i].position[2];

            let dist_sq = dx * dx + dy * dy + dz * dz;
            let dist = dist_sq.sqrt();

            // BUG 1: Newton's law requires F = G*m1*m2/r^2, so the vector form
            // needs division by r^3 (because F_vec = F * r_hat = F * dr/|dr|).
            // This incorrectly divides by dist^2 instead of dist^3, making the
            // force proportional to 1/r instead of 1/r^2.
            let factor = g * bodies[j].mass / (dist * dist);

            accel[i][0] += factor * dx;
            accel[i][1] += factor * dy;
            accel[i][2] += factor * dz;
        }
    }

    accel
}

/// Compute kinetic energy of a single body: KE = 0.5 * m * |v|^2
fn kinetic_energy(body: &Body) -> f64 {
    let v = &body.velocity;
    0.5 * body.mass * (v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
}

/// Compute potential energy for a body relative to all others.
/// Uses factor of 0.5 to avoid double-counting pairs.
fn potential_energy_for_body(bodies: &[Body], index: usize, g: f64) -> f64 {
    let mut pe = 0.0;
    for j in 0..bodies.len() {
        if j == index {
            continue;
        }
        let dx = bodies[j].position[0] - bodies[index].position[0];
        let dy = bodies[j].position[1] - bodies[index].position[1];
        let dz = bodies[j].position[2] - bodies[index].position[2];
        let dist = (dx * dx + dy * dy + dz * dz).sqrt();

        // BUG 4: Gravitational potential energy is PE = -G*m1*m2/r (negative).
        // This incorrectly uses a positive sign, breaking energy conservation.
        pe += 0.5 * g * bodies[index].mass * bodies[j].mass / dist;
    }
    pe
}

/// Compute total energy of the system (KE + PE).
fn total_energy(bodies: &[Body], g: f64) -> f64 {
    let mut energy = 0.0;
    for i in 0..bodies.len() {
        energy += kinetic_energy(&bodies[i]);
        energy += potential_energy_for_body(bodies, i, g);
    }
    energy
}

/// Record the current state of all bodies.
fn record_state(bodies: &[Body], time: f64, g: f64) -> StepRecord {
    let mut body_states = Vec::new();
    for i in 0..bodies.len() {
        body_states.push(BodyState {
            position: bodies[i].position,
            velocity: bodies[i].velocity,
            ke: kinetic_energy(&bodies[i]),
            pe: potential_energy_for_body(bodies, i, g),
        });
    }
    StepRecord {
        time,
        bodies: body_states,
        total_energy: total_energy(bodies, g),
    }
}

/// Check for collisions between bodies at the current step.
fn check_collisions(bodies: &[Body], step: usize, threshold: f64) -> Vec<CollisionEvent> {
    let mut events = Vec::new();
    let n = bodies.len();
    for i in 0..n {
        for j in (i + 1)..n {
            let dx = bodies[j].position[0] - bodies[i].position[0];
            let dy = bodies[j].position[1] - bodies[i].position[1];
            let dz = bodies[j].position[2] - bodies[i].position[2];
            let dist = (dx * dx + dy * dy + dz * dz).sqrt();
            if dist < threshold {
                events.push(CollisionEvent {
                    step,
                    body_a: i,
                    body_b: j,
                    distance: dist,
                });
            }
        }
    }
    events
}

/// Check for continuous collisions between bodies during a step using linear interpolation.
///
/// This function is supposed to find the minimum approach distance during the step
/// by computing the true minimum of |r(t)|^2 over t in [0,1], where:
///   r(t) = (p2 - p1) + (v2 - v1) * t * dt
///
/// The correct formula for the optimal t is:
///   t* = -dot(r0, dv*dt) / dot(dv*dt, dv*dt), clamped to [0,1]
///
/// BUG: This implementation only checks t=0.5 (the midpoint of the step) instead of
/// computing the actual minimum. Fast-moving bodies can pass closest approach at any
/// t in [0,1], so checking only t=0.5 will miss many tunneling collisions.
pub fn check_continuous_collision(
    body_i: &Body,
    body_j: &Body,
    step: usize,
    threshold: f64,
    dt: f64,
) -> Option<CollisionEvent> {
    let r0 = [
        body_j.position[0] - body_i.position[0],
        body_j.position[1] - body_i.position[1],
        body_j.position[2] - body_i.position[2],
    ];
    let dv = [
        body_j.velocity[0] - body_i.velocity[0],
        body_j.velocity[1] - body_i.velocity[1],
        body_j.velocity[2] - body_i.velocity[2],
    ];

    // BUG: Only checks midpoint t=0.5 instead of computing actual minimum t*.
    // The correct approach is: t* = -dot(r0, dv*dt) / dot(dv*dt, dv*dt)
    // clamped to [0,1]. This midpoint check misses collisions where closest
    // approach occurs at t != 0.5.
    let t_check = 0.5_f64;

    let rx = r0[0] + dv[0] * t_check * dt;
    let ry = r0[1] + dv[1] * t_check * dt;
    let rz = r0[2] + dv[2] * t_check * dt;
    let dist_at_t = (rx * rx + ry * ry + rz * rz).sqrt();

    if dist_at_t < threshold {
        Some(CollisionEvent {
            step,
            body_a: 0, // placeholder; caller fills in correct indices
            body_b: 1,
            distance: dist_at_t,
        })
    } else {
        None
    }
}

/// Run the n-body simulation with Velocity Verlet integration.
pub fn run_simulation(seed: &SeedData) -> SimOutput {
    let config = &seed.config;
    let dt = config.dt;
    let g = config.gravitational_constant;
    let threshold = config.collision_threshold;

    let mut bodies = seed.bodies.clone();
    let n = bodies.len();

    let mut accel = compute_accelerations(&bodies, g);

    let mut steps = Vec::new();
    let mut collisions = Vec::new();

    for step in 0..=config.num_steps {
        // Record current state
        steps.push(record_state(&bodies, step as f64 * dt, g));

        // Check for close approaches at end of step
        collisions.extend(check_collisions(&bodies, step, threshold));

        // Check for continuous (mid-step) collisions to catch tunneling
        if step < config.num_steps {
            let n_bodies = bodies.len();
            for i in 0..n_bodies {
                for j in (i + 1)..n_bodies {
                    if let Some(mut event) = check_continuous_collision(
                        &bodies[i],
                        &bodies[j],
                        step,
                        threshold,
                        dt,
                    ) {
                        event.body_a = i;
                        event.body_b = j;
                        // Only record if end-of-step check didn't already catch it
                        let already_detected = collisions.iter().any(|c| {
                            c.step == step && c.body_a == i && c.body_b == j
                        });
                        if !already_detected {
                            collisions.push(event);
                        }
                    }
                }
            }
        }

        if step == config.num_steps {
            break;
        }

        // Velocity Verlet integration
        //
        // BUG 2: The correct Velocity Verlet order is:
        //   1. Update POSITIONS using current velocity and acceleration
        //   2. Compute NEW accelerations at the updated positions
        //   3. Update VELOCITIES using the average of old and new accelerations
        //
        // This implementation incorrectly:
        //   1. Computes new accelerations at the OLD positions
        //   2. Updates velocities first
        //   3. Then updates positions using the already-modified velocity

        // BUG 2: Computing accelerations at old positions (should be after pos update)
        let accel_new = compute_accelerations(&bodies, g);

        // BUG 2: Updating velocities before positions
        for i in 0..n {
            for k in 0..3 {
                bodies[i].velocity[k] +=
                    0.5 * (accel[i][k] + accel_new[i][k]) * dt;
            }
        }

        // BUG 3: Position update multiplies velocity by dt*dt instead of dt.
        // Correct: pos += vel * dt + 0.5 * accel * dt^2
        // Bug:     pos += vel * dt * dt + 0.5 * accel * dt^2
        for i in 0..n {
            for k in 0..3 {
                bodies[i].position[k] +=
                    bodies[i].velocity[k] * dt * dt
                    + 0.5 * accel_new[i][k] * dt * dt;
            }
        }

        accel = accel_new;
    }

    SimOutput { steps, collisions }
}

/// Validate seed data for correctness. Returns Ok(()) or an error message.
pub fn validate_seed(seed: &SeedData) -> Result<(), String> {
    if seed.config.dt <= 0.0 {
        return Err("Timestep (dt) must be positive".to_string());
    }
    if seed.config.num_steps == 0 {
        return Err("Number of steps must be positive".to_string());
    }
    if seed.config.gravitational_constant <= 0.0 {
        return Err("Gravitational constant must be positive".to_string());
    }
    if seed.config.collision_threshold < 0.0 {
        return Err("Collision threshold must be non-negative".to_string());
    }
    if seed.bodies.is_empty() {
        return Err("At least one body is required".to_string());
    }
    for (i, body) in seed.bodies.iter().enumerate() {
        if body.mass <= 0.0 {
            return Err(format!("Body {} has non-positive mass: {}", i, body.mass));
        }
    }
    Ok(())
}
