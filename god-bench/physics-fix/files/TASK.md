# RK45 Dense-Output Event Localization

Edit only `src/event.rs`. The supplied crate contains the ODE systems, adaptive Dormand-Prince RK45 integrator, dense-step interpolation, and physical wrappers. Implement `localize_event` to find the first event within one accepted step.

The event may represent pressure reaching zero, a surface crossing its horizon, or collapse reaching its cutoff. Respect rising/falling/any direction, accept roots at either endpoint, evaluate returned state through `DenseStep::evaluate`, and return `None` when the endpoint values do not bracket an allowed crossing. Localization must remain accurate when values are badly scaled, an endpoint is nearly zero, or a secant proposal is unsafe. Use a safeguarded method with a bisection fallback and terminate using both the supplied time and value tolerances. Results must be finite and deterministic.

Do not edit the integrator or add dependencies. The expected solution changes roughly 60-120 lines.

Build with `cp /app/files/Cargo.toml /app/Cargo.toml && rm -rf /app/src && cp -r /app/files/src /app/src && cd /app && cargo test --release --offline`.

Run `python3 -m pytest -q /app/files/tests.py`.
