use serde::{Deserialize, Serialize};

/// A body in the simulation with mass, position, and velocity.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Body {
    pub mass: f64,
    pub position: [f64; 3],
    pub velocity: [f64; 3],
}

/// Configuration for the simulation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SimConfig {
    pub dt: f64,
    pub num_steps: usize,
    pub collision_threshold: f64,
    pub gravitational_constant: f64,
}

/// State of a single body at a given timestep.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BodyState {
    pub position: [f64; 3],
    pub velocity: [f64; 3],
    pub ke: f64,
    pub pe: f64,
}

/// Record of simulation state at a single timestep.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StepRecord {
    pub time: f64,
    pub bodies: Vec<BodyState>,
    pub total_energy: f64,
}

/// A collision event between two bodies.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CollisionEvent {
    pub step: usize,
    pub body_a: usize,
    pub body_b: usize,
    pub distance: f64,
}

/// Complete simulation output.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SimOutput {
    pub steps: Vec<StepRecord>,
    pub collisions: Vec<CollisionEvent>,
}

/// Input seed data containing initial conditions and configuration.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SeedData {
    pub config: SimConfig,
    pub bodies: Vec<Body>,
}

/// Summary statistics for a single simulation run (used in batch mode).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SimSummary {
    pub seed_file: String,
    pub initial_energy: f64,
    pub final_energy: f64,
    pub energy_drift: f64,
    pub collision_count: usize,
    pub final_positions: Vec<[f64; 3]>,
    pub num_steps: usize,
}
