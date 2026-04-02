# CIFAR-10 PyTorch Baseline with ONNX Export

Train a CIFAR-10 classifier with PyTorch (torch==2.5.1) and export it to ONNX for inference.

- Train data: `/app/files/cifar_tiny.npz`
- Visible test data: `/app/files/cifar_public_test.npz`

## Required outputs in `/app/files`

- `model.onnx` — ONNX export of the trained model
- `infer.py` — inference script using onnxruntime (not PyTorch)

## Required inference command contract

```
python3 /app/files/infer.py --model /app/files/model.onnx --input-npz <images_npz> --output-npy <preds_npy>
```

- The inference script must use `onnxruntime` (not `torch`) to load and run the ONNX model.
- Predictions must be deterministic class IDs in `[0, 9]`.
- The input npz files use the key `test_images` for the image array.

## Requirements

- **Minimum accuracy: 0.65 (65%)** on both the public test set and a held-out validation set. If your accuracy is below 60%, iterate on the model architecture — try more layers, batch normalisation, data augmentation, or a wider channel count.
- Model must be small: `model.onnx` must be under 100 KB (100,000 bytes).
- Training must complete within 180 seconds on 8 CPU cores.
- Inference must be deterministic — seed all randomness (Python, NumPy, PyTorch) and use deterministic algorithms.

## Self-verification (important!)

After training, verify your model meets the accuracy threshold:

    python3 -m pytest /app/files/tests.py -v

Do NOT use `python3 tests.py` — test files require pytest. Running them directly with python silently does nothing. If any test fails, improve your model and re-export.

## Constraints

- Work offline in the container.
- Keep outputs deterministic.
- Do not modify test files.
