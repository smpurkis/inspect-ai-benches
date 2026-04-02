# CIFAR-10 Step 1 (PyTorch baseline + ONNX export)

Train a CIFAR-10 classifier with PyTorch (torch==2.5.1) and export it to ONNX for inference.

- Train data: `/app/step_1/files/cifar_tiny.npz`
- Visible test data: `/app/step_1/files/cifar_public_test.npz`

## Required outputs in `/app/step_1/files`

- `model.onnx` — ONNX export of the trained model
- `infer.py` — inference script using onnxruntime (not PyTorch)
- `pytorch_public_test_preds.npy` — predictions on the public test set

## Required inference command contract

```
python3 /app/step_1/files/infer.py --model /app/step_1/files/model.onnx --input-npz <images_npz> --output-npy <preds_npy>
```

- The inference script must use `onnxruntime` (not `torch`) to load and run the ONNX model.
- Predictions must be deterministic class IDs in `[0, 9]`.
- The input npz files use the key `test_images` for the image array.

## Requirements

All constraints and limits are defined in `/app/step_1/files/train_config.json`. Key requirements:
- **Minimum accuracy: 0.55 (55%) on both the public test set and a held-out validation set.** Your model must achieve at least 55% classification accuracy. Evaluate on the public test set after training and check the accuracy before submitting. If your accuracy is below 55%, improve the model architecture and training while keeping the run deterministic.
- Training must use at most 8 CPU cores and at most 180 seconds (3 minutes) elapsed training time.
- Model must have at most 100,000 trainable parameters (model.onnx must be under 1 MB). Keep the architecture small — a simple 2–3 layer CNN with narrow channels (e.g. 16→32 filters) fits comfortably within this budget.
- Use the fixed seed from `train_config.json` and make training deterministic: seed Python, NumPy, and PyTorch, enable deterministic algorithms where supported, and avoid unseeded randomness.
- Use deterministic data loading (`num_workers=0` and a seeded sampler/generator if you shuffle). Do not rely on random augmentation unless it is fully seed-driven.

## Self-verification (important!)

After training, verify your model meets the accuracy threshold:

    python3 -m pytest /app/step_1/files/tests.py -v

Do NOT use `python3 tests.py` — test files require pytest. Running them directly with python silently does nothing. If any test fails, improve your model and re-export before completing this step.

## Scoring

- Step 1 fail → 0
- Step 1 pass, Step 2 fail → 1/3
- Step 1+2 pass, Step 3 fail → 2/3
- All pass → 1.0

## Constraints

- Work offline in the container.
- Keep outputs deterministic.
- Do not modify test files under `/app/step_*/files/tests.py` (they are read-only).
