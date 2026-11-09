//! Trusted deterministic trainer policy integration.
use crate::training_policy::{augmentation, class_weights, learning_rate, prefer_checkpoint, CheckpointMetrics};

pub fn epoch_plan(seed: u64, epoch: u64, total: u64, counts: [u64; 10], sample_ids: &[u64]) -> Result<(f64, [f64; 10], usize), &'static str> {
    let rate = learning_rate(0.1, epoch, total)?;
    let weights = class_weights(counts)?;
    let flipped = sample_ids.iter().filter(|&&id| augmentation(seed, epoch, id).flip).count();
    Ok((rate, weights, flipped))
}

pub fn select_checkpoint(candidate: CheckpointMetrics, current: Option<CheckpointMetrics>) -> Result<bool, &'static str> {
    prefer_checkpoint(candidate, current)
}
