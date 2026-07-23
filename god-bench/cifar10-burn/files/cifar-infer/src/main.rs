mod model;

use std::{
    env,
    error::Error,
    ffi::OsStr,
    fs::File,
    path::{Path, PathBuf},
};

use burn::{
    backend::NdArray,
    module::Module,
    record::{FullPrecisionSettings, NamedMpkFileRecorder},
    tensor::{Tensor, TensorData},
};
use ndarray::{Array1, Array4};
use ndarray_npy::{NpzReader, WriteNpyExt};

use model::CifarModel;

type Backend = NdArray<f32>;

fn argument(name: &str) -> Result<String, Box<dyn Error>> {
    let mut args = env::args().skip(1);
    while let Some(value) = args.next() {
        if value == name {
            return args.next().ok_or_else(|| format!("missing value for {name}").into());
        }
    }
    Err(format!("missing required argument {name}").into())
}

fn record_base(path: &Path) -> PathBuf {
    if path.extension() == Some(OsStr::new("mpk")) {
        path.with_extension("")
    } else {
        path.to_path_buf()
    }
}

fn main() -> Result<(), Box<dyn Error>> {
    let input_path = argument("--input-npz")?;
    let output_path = argument("--output-npy")?;
    let model_path = Path::new(env!("CARGO_MANIFEST_DIR")).join("model.mpk");

    let mut archive = NpzReader::new(File::open(input_path)?)?;
    let images: Array4<f32> = archive.by_name("test_images")?;
    let [count, channels, height, width]: [usize; 4] = images
        .shape()
        .try_into()
        .map_err(|_| "test_images must have four dimensions")?;
    if channels != 3 || height != 32 || width != 32 {
        return Err("test_images must have shape [N, 3, 32, 32]".into());
    }

    let device = Default::default();
    let recorder = NamedMpkFileRecorder::<FullPrecisionSettings>::new();
    let model = CifarModel::<Backend>::new(&device).load_file(
        record_base(&model_path),
        &recorder,
        &device,
    )?;
    let (values, offset) = images.into_raw_vec_and_offset();
    if offset.unwrap_or(0) != 0 {
        return Err("test_images must be contiguous".into());
    }
    let input = Tensor::<Backend, 4>::from_data(
        TensorData::new(values, [count, channels, height, width]),
        &device,
    );
    let predicted = model.forward(input).argmax(1).squeeze_dim::<1>(1);
    let classes = predicted.to_data().to_vec::<i64>()?;
    let classes = classes.into_iter().map(|value| value as u8).collect::<Vec<_>>();
    Array1::from_vec(classes).write_npy(File::create(output_path)?)?;
    Ok(())
}
