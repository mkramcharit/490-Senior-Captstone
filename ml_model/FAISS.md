# ML recognition and FAISS

The completed reference collection contains 1,273,627 images representing 35,070 Neon landmark IDs. DINOv2-small converts each image into a normalized 384-value CLS embedding. The runtime index uses 8-bit scalar quantization; the full-precision master and resumable build ledger are retained separately. The reference mapping preserves the original `training_data.landmark_id` values.

## Install and check

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
$env:LANDMARK_INDEX_PATH = "artifacts/ML/indexes/full-neon/handoff"
$env:LANDMARK_MODEL_PATH = "dinov2-small"
.\.venv\Scripts\python.exe -m landmark_ml check
```

On another computer, extract the shared runtime index and point `LANDMARK_INDEX_PATH` at the directory containing `images.faiss` and `references.json`. The model directory must contain `config.json`, `preprocessor_config.json`, and `model.safetensors`. The model and index signatures must match. The check command prints the resolved paths, reference count, landmark count, dimensions, calibration status, and available checksum verification. Older bundles without a checksum manifest remain loadable but are identified as unverified.

The adapter prefers the full index when no explicit path is set. It never silently selects the old 15-reference demonstration index. Explicit arguments and environment settings take precedence. Restart the service or call `clear_model_cache()` after replacing an installed bundle.

## Run a prediction

```powershell
.\.venv\Scripts\python.exe -m landmark_ml predict artifacts/ML/indexes/full-neon/handoff "C:/path/to/photo.jpg" --model dinov2-small
```

```python
from landmark_ml import predict_image, recognize_image

result = predict_image(uploaded_bytes)
landmark_id, confidence = recognize_image(uploaded_bytes)
```

The detailed response includes:

- `landmark_id`: the selected catalog ID, or null when the recognition policy rejects the evidence.
- `prediction_status`: `candidate` or `unknown`. Passing a retrieval rule does not guarantee correctness.
- `candidate_landmark_id`: the nearest candidate retained for diagnosis, even when the public result is unknown.
- `match_score`: nonnegative winning similarity multiplied by the fraction of retrieved references supporting the winner. It is not a correctness probability.
- `confidence` and `confidence_probability`: the same estimated correctness probability when compatible calibration exists; otherwise null. The tuple adapter preserves null.
- `confidence_calibrated`: whether compatible calibration was applied to this prediction.
- `confidence_validation_scope`: the evaluated population and limits of the installed probability model.
- `top_matches`: retrieved reference IDs, scores, and image identifiers. `neon:<id>` identifiers are provenance keys, not local image filenames.
- `index_info`: the actual loaded bundle location, reference count, landmark count, and embedding dimension.

Unknown results must not be looked up as a landmark. A null confidence must not be converted into a percentage. Frontend/backend code must handle these two cases explicitly. The ML code does not change those application layers.

The default recognition policy requires sufficient similarity, supporting references, and separation from competing landmarks, with a separate near-duplicate rule. These are heuristic rejection rules. They reduce forced guesses; they are not an accuracy guarantee. The policy can be saved with the bundle as `recognition-policy.json`.

## Export a verified runtime bundle

```powershell
.\.venv\Scripts\python.exe -m landmark_ml package artifacts/ML/sharing/current/faiss-runtime.zip --index artifacts/ML/indexes/full-neon/handoff
```

Choose an unused output filename. Export verifies that the mapping and index load with the selected model, includes SHA-256 checksums in `ml-version.json`, and reads every exported file back to verify it. Loading an exported bundle checks these hashes and rejects modified or unlisted runtime configuration. Checksums detect corruption or mismatched files; they do not authenticate an untrusted sender.

The ZIP contains the runtime index, JSON mapping, and available build, validation, policy, and calibration files. It excludes image archives, checkpoints, Python environments, and the duplicate `landmarks.index` alias. Send the DINOv2 model separately when the teammate does not already have it. The old pickle mapping is unnecessary for `LandmarkPipeline`, which uses JSON.

## Calibration and evaluation

The production index includes an approved, independently evaluated web-photo calibrator. Confidence is an estimated probability that the selected catalog identity is correct, conditional on acceptance and the supported score range. Rejected predictions and scores outside that range return null. The old three-landmark calibrator must not be copied onto this index. Restart the service after installing the updated ML code and calibration artifact.

```powershell
.\artifacts\gpu-runtime\Scripts\python.exe scripts/calibrate_full_index.py artifacts/ML/indexes/full-neon/handoff artifacts/ML/evaluations/new-confidence-run --device cuda --per-split 400 --population accepted_predictions --exclude-test-manifest artifacts/ML/evaluations/calibration-full-v2/manifest.json
```

Use the CPU environment and `--device cpu` if CUDA is unavailable. This experiment collects official GLDv2 Public examples to fit calibration and separate Private examples to evaluate it. Each split balances covered-landmark and unsupported/non-landmark queries. Previously inspected test examples can be excluded. Image IDs overlapping the index are excluded, as are exact and perceptually similar images within the query collection. Visual duplicates against every training image have not been exhaustively audited.

Collection and prediction checkpoints support restarting the same command. A changed experiment configuration requires a new output directory. The experiment writes `manifest.json`, `predictions.json`, `evaluation.json`, and a calibration candidate when fitting is supported by sufficient correct and incorrect examples. Candidates are marked unapproved and cannot be loaded as runtime calibration. If fitting is unsupported, the report states why and retains recognition results. Nothing is installed automatically.

Evaluate probabilities on the population that receives them: accepted predictions within the fitted score range. Review sample counts, Brier score, reliability bins and their uncertainty, acceptance coverage, and unsupported false acceptance. Benchmark results are limited to their sampling population. Actual frontend upload examples with verified ground truth are still needed before claiming that percentages are reliable for arbitrary uploads.

The compact-index validation found approximately 99.3% neighbor recall at 10 and 100% landmark-decision agreement on 256 reference queries compared with the full-precision master, excluding each query itself. These measure compression fidelity, not recognition accuracy.

### October 29 web-photo validation

`artifacts/ML/evaluations/web-confidence-v2` contains the current validation evidence. The previous official GLDv2 experiment and the failed first web-photo validation remain preserved; their results were not discarded or presented as passed tests.

The replacement sigmoid calibrator was fitted on 158 accepted predictions from 453 reviewed development photos: 130 correct and 28 incorrect. Grouped cross-validation selected the score-only model over the additional-feature model. The candidate and statistical checks were frozen before running the fresh confirmation cohort.

The confirmation set contains 367 reviewed Wikimedia Commons and Flickr photos across 19 landmarks. Google Images was blocked by CAPTCHA, so the source images were collected directly from public providers. Exact source identities and hashes were checked against all 1,273,627 reference provenance records. Query near-duplicates were removed, including development-photo matches. Seven test photos share a site and photographer with development sources but come from capture dates more than 31 days apart; the remaining 360 do not share that combination. Capture dates are provider metadata, and exhaustive visual-duplicate checks against every reference image were unavailable. This is a selected benchmark, not a random sample of frontend uploads.

Of 367 test photos, 130 predictions passed recognition rules and 125 were within the evaluated calibration score range. Those 125 predictions were 85.6% correct, with expected calibration error 0.0299 using five fixed bins and Brier score 0.0973. The raw-score Brier score on the same subset was 0.0967: calibration did not demonstrate an improvement over raw scores here, but passed the predeclared noninferiority check. A constant development-accuracy baseline scored 0.1244. The 95% source-group bootstrap interval for mean probability bias was -5.4 to +5.8 percentage points.

The 105 predictions in the 80–100% bin averaged 90.8% estimated confidence and were 91.4% correct. Lower bins contain only 3, 6, and 11 examples, so their estimates remain uncertain. The evidence supports aggregate calibration on comparable photos; it does not prove that every individual percentage, landmark, or arbitrary upload is accurate.

Recognition remains imperfect: 14 of 134 unsupported-landmark photos were falsely accepted (10.4%; 95% interval 6.3–16.8%). That recognition check failed and is reported separately from probability-calibration approval. A calibrated percentage does not add missing catalog landmarks or guarantee a correct identification.

Evidence files:

- `validation/evaluation.json`: frozen input hashes, probability metrics, uncertainty intervals, and all pass/fail checks.
- `validation/predictions.json`: individual outcomes and source labels.
- `validation/approved-calibration.json`: approved parameters bound to this exact index and model.
- `report/reliability.png`: confidence versus observed correctness, with bin counts and uncertainty.
- `source-audit.json`, `annotation-decisions.json`, and `manifest.json`: source provenance, exclusions, and reviewed labels.
- `fit/selection.json`: development-only model selection.

For a new candidate, collect and verify separate development and test images, fit only on development data, and freeze the candidate hash and checks before inference. The scripts below refuse unapproved or failed calibration deployment:

```powershell
.\artifacts\gpu-runtime\Scripts\python.exe scripts/validate_confidence.py <index> <candidate.json> <test-manifest.json> <frozen-protocol.json> <new-validation-output> --device cuda
.\.venv\Scripts\python.exe scripts/install_calibration.py <index> <approved-calibration.json> <evaluation.json>
```

Approval is scoped to the recorded benchmark and configuration. Changing embeddings, reference vectors, labels, search settings, or recognition rules requires reevaluation. Keep `ml-version.json` synchronized when replacing calibration in a checksum-protected bundle; the installation script updates it automatically.

## Build, resume, and extend

The completed source pass is retained under `artifacts/ML/indexes/full-neon`. Its ledger and full-precision master provide row-level coverage and provenance. Do not rebuild it merely to run predictions.

For a separate URL-based pilot, `scripts/index_neon.py` reads the configured Neon database without changing rows. It writes checkpoints, failures, sources, and mappings; `--resume` requires the same database, model, and landmark selection. A pilot containing no readable images fails with an explicit error and keeps its failure logs.

For an archive-based full build, `scripts/run_index.py <new-output-directory>` selects CUDA when available and CPU otherwise, supervises resumable archive processing, and exports the compact handoff after coverage checks. Storage guards reserve free space on the destination drive and C drive. Downloads use a bounded rolling archive cache; original reference photos are not all retained locally.

`scripts/add_references.py` can extend the reference collection only after verifying the intended landmark already has a matching real Neon record. New embeddings invalidate prior calibration. Missing catalog identities require the database teammate to supply the correct records and IDs first. Adding images under a similar but incorrect landmark ID would corrupt recognition.

## Local storage and verification

On this machine, `artifacts/ML` is a junction to `D:/Trekmark-ML/workspace`. Large indexes, evaluations, and sharing ZIPs live on D. The source code remains in the C-drive project. `artifacts/` and environments remain Git-ignored. The DINOv2 folder is tracked as a Git link rather than ordinary model files. A source checkout alone does not guarantee the runtime assets are present; install the index ZIP and model weights separately.

The local compatibility junction `artifacts/landmarks` also points to the full runtime index. The former 15-reference demo remains archived on D. On another machine, extract the runtime ZIP to the configured index directory; these local junctions are not distributed through Git.

```powershell
.\.venv\Scripts\python.exe -m pytest ml_model/tests
```

The suite covers normalized embeddings, real local model inference when installed, retrieval and batched search, rejection behavior, calibration compatibility, mapping integrity, resumable indexing, source accounting, storage guards, and portable bundle checksums.
