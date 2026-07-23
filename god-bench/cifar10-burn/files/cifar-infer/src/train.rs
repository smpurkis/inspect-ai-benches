mod model;

use std::{
    env,
    error::Error,
    ffi::OsStr,
    fs,
    path::{Path, PathBuf},
};

use burn::{
    backend::NdArray,
    module::Module,
    record::{FullPrecisionSettings, NamedMpkFileRecorder},
    tensor::backend::Backend,
};

use model::CifarModel;

type TrainBackend = NdArray<f32>;

fn argument(name: &str) -> Result<String, Box<dyn Error>> {
    let mut args = env::args().skip(1);
    while let Some(value) = args.next() {
        if value == name {
            return args.next().ok_or_else(|| format!("missing value for {name}").into());
        }
    }
    Err(format!("missing required argument {name}").into())
}

fn config_seed(path: &str) -> Result<u64, Box<dyn Error>> {
    for line in fs::read_to_string(path)?.lines() {
        if let Some(value) = line.strip_prefix("seed =") {
            return Ok(value.trim().parse()?);
        }
    }
    Err("training config must define seed".into())
}

fn record_base(path: &Path) -> PathBuf {
    if path.extension() == Some(OsStr::new("mpk")) {
        path.with_extension("")
    } else {
        path.to_path_buf()
    }
}

fn main() -> Result<(), Box<dyn Error>> {
    let train_path = argument("--train-npz")?;
    let config_path = argument("--config")?;
    let model_path = argument("--model-out")?;
    if !Path::new(&train_path).is_file() {
        return Err("training archive does not exist".into());
    }

    let device = Default::default();
    TrainBackend::seed(&device, config_seed(&config_path)?);
    let model = CifarModel::<TrainBackend>::new(&device);

    // Starter baseline: replace this deterministic initialization with training
    // over train_images and train_labels from the supplied archive.
    model.save_file(
        record_base(Path::new(&model_path)),
        &NamedMpkFileRecorder::<FullPrecisionSettings>::new(),
    )?;
    Ok(())
}
