# Execution Plan 11.5 Log

Reset date: 2026-04-07
Plan file: `docs/ExecutionPlan11.5.md`

## Active Reset Record

- `2026-04-07 00:00:00 -05:00` - Active execution log restarted after renaming the previous baseline log to `docs/Archive/ExecutionPlan11.5_old_baseline.md`.
- `2026-04-07 00:00:00 -05:00` - Archived `docs/ExecutionPlan11.5.3.md`, `docs/ExecutionPlan11.5.1_log.md`, `docs/ExecutionPlan11.5.2_log.md`, and `docs/ExecutionPlan11.5.3_log.md` under `docs/Archive/`.
- `2026-04-07 00:00:00 -05:00` - Active Execution Plan 11.5 tracking remains Gemma-only.

## Step 0.1 - Reset Active Tracking And Identity

- Active plan/log filenames now consist of `docs/ExecutionPlan11.5.md` and this file.
- Previous baseline tracking was moved to `docs/Archive/ExecutionPlan11.5_old_baseline.md`.
- Active dependency manifests and the active plan/log no longer carry hard-coded legacy model IDs.

## Step 0.2 - Toolchain Preflight For Gemma 4B-Class Loading

- Preflight executed with `PYTHONUSERBASE=D:\AI\rComp\dist\pyuser` so the Gemma-capable stack could be installed on `D:` instead of the nearly full system `C:` drive.
- Resolved package set:
  - `transformers==5.5.0`
  - `tokenizers==0.22.2`
  - `accelerate==1.13.0`
  - `peft==0.18.1`
  - `bitsandbytes==0.49.2`
  - `huggingface_hub==1.9.1`
  - `torch==2.4.1`
  - `torchvision==0.19.1`
  - `sentence-transformers==5.3.0`
  - `trl==1.0.0`
  - `typer==0.24.1`
- `AutoConfig.from_pretrained('google/gemma-4-E4B-it')` succeeded with `gemma-config-ok`.
- Checked-in dependency manifests were updated to match the Gemma-capable stack:
  - `pyproject.toml`
  - `requirements-gpu.txt`
  - `scripts/training/prepare_qlora_env.ps1`

## Step 0.3 - Authenticated Download Readiness And Cache Location

- Cache location established:
  - `HF_HOME=D:\AI\rComp\dist\hf_cache`
  - `HUGGINGFACE_HUB_CACHE=D:\AI\rComp\dist\hf_cache\hub`
- Authenticated Hugging Face access is now configured and `hf auth whoami` returns `user=cfrydenlund01`.
- Hugging Face credentials are now available through:
  - Windows Credential Manager entries `HuggingFace:HF_TOKEN` and `HuggingFace:token`
  - workspace token file `dist/hf_cache/token`
- `hf download google/gemma-4-E4B-it --local-dir D:\AI\rComp\dist\models\gemma-4-e4b-it` completed and populated:
  - `dist/models/gemma-4-e4b-it/config.json`
  - `dist/models/gemma-4-e4b-it/tokenizer.json`
  - `dist/models/gemma-4-e4b-it/model.safetensors`
- Downloaded primary weight artifact size: `15,992,595,884` bytes.
- Temporary plaintext secret files used during setup were removed from `docs/Archive` and `docs/proposal`.

## Step 0.4 - Build The Active Training Config

- Updated existing Step 0.4 artifacts using current approved snapshot/corpus chain values:
  - `config/training_first_pass.example.json`
  - `dist/training/current_training_config.json`
- `dist/training/current_training_config.json` is now minimal execution-ready and pinned to:
  - `base_model=google/gemma-4-E4B-it`
  - `run_id=gemma4-e4b-ear-2026-04-07-snapshot-ecfr_current_20260210_1627_parts_736_740_742_744_746-v1`
  - `snapshot_manifest=snapshots/offline/ecfr_current_20260210_1627_parts_736_740_742_744_746/manifest.json`
  - `snapshot_id=ecfr_current_20260210_1627_parts_736_740_742_744_746`
  - `snapshot_sha256=bc9db4287a2271058d4860e98ca538849ed4645ae6515694f9fb31a755d91678`
  - `retrieval_corpus=data/faiss/retrieval_corpus.jsonl`
  - `training_input_contract=config/training_input_contract.example.json`
  - `index_meta=data/faiss/index.meta.json`
  - `use_4bit=true` and `require_qlora_4bit=true`
- Retained and hardened existing validators in `scripts/training/run_phase5_finetune.py`:
  - added preflight rejection for placeholder snapshot fields (`snapshot_manifest`, `snapshot_id`, `snapshot_sha256`) before snapshot extraction/manifest resolution.
- Validator coverage updated and passing:
  - `py -3 -m pytest -q tests/tooling/test_phase5_training_runner.py` -> `10 passed`
- Execution-readiness proof run:
  - `py -3 scripts/training/run_phase5_finetune.py --config dist/training/current_training_config.json --prepare-only`
  - output: `dist/training/gemma4-e4b-ear-2026-04-07-snapshot-ecfr_current_20260210_1627_parts_736_740_742_744_746-v1/`
  - includes `manifest.json`, `examples.jsonl`, `run_config.json`, and `run_metadata.json`
  - `run_config.json` confirms `base_model=google/gemma-4-E4B-it` and `qlora.required=true`

## Current Status

- Step `0.1` is complete.
- Step `0.2` is complete.
- Step `0.3` is complete.
- Step `0.4` is complete.
- Remaining plan commands should continue with `PYTHONUSERBASE=D:\AI\rComp\dist\pyuser` until the system-wide Python package set is brought up to the same versions.

## Step 1.1 - Prepare-Only Packaging

- Executed prepare-only run with the active config: `py -3 scripts/training/run_phase5_finetune.py --config dist/training/current_training_config.json --prepare-only`.
- Output package: `dist/training/gemma4-e4b-ear-2026-04-07-snapshot-ecfr_current_20260210_1627_parts_736_740_742_744_746-v1/`.
- Evidence captured:
  - `manifest.json` (manifest_version `training-package.v1`, base_model `google/gemma-4-E4B-it`, snapshot_sha256 `bc9db4...1678`, retrieval_corpus_digest `978ad2f9...03a6c`, example_count `256`, examples_sha256 `3f957d...c378`).
  - `run_config.json` (prepare_only `true`, qlora.required `true`, use_4bit `true`).
  - `run_metadata.json` (status `prepare_only`, qlora evidence status `not_executed_prepare_only`).

## Step 1.2 - Validate Prepared Package Metadata

- Validation scope uses existing Phase 5.3 training runner tests.
- Command: `py -3 -m pytest -q tests/tooling/test_phase5_training_runner.py`
- Result: `10 passed` (includes preflight, snapshot/corpus integrity, QLoRA gating, and placeholder field rejection).

## Phase 2 - Execute First Gemma 4B-Class Training Candidate

- `2026-04-07 10:16:58 -05:00` - Attempted full QLoRA run: `py -3 scripts/training/run_phase5_finetune.py --config dist/training/current_training_config.json --use-4bit --require-qlora-4bit`.
- Result: **failed preflight**. Training runner halted because CUDA-capable PyTorch is required for the Gemma 4B QLoRA path but the environment reports `torch=2.4.1+cpu`, `cuda_available=False`, `cuda_device_count=0`.
- Next action to unblock Phase 2: install a CUDA-enabled Torch build on hardware with at least one visible CUDA device (matching the installed CUDA toolkit/driver), then rerun Step 2.1.
- `2026-04-07 11:25:00 -05:00` - Installed CUDA-enabled PyTorch + torchvision wheels (`torch==2.6.0+cu124`, `torchvision==0.21.0+cu124`) into `D:\AI\rComp\dist\pyuser`.
- `2026-04-07 11:40:00 -05:00` onward - Multiple Step 2.1 attempts with 4-bit QLoRA continue to fail during `Trainer` setup because the model is auto-offloading layers to CPU/disk, leaving `meta` tensors that `accelerate` refuses to train (`NotImplementedError: Cannot copy out of meta tensor`). Model load also crashes when forcing full GPU placement (`device_map=None` / `{"":0}`) on the 8 GB RTX 2070.
- Interim mitigation attempts:
  - Added unwrap of `Gemma4ClippableLinear` wrappers so LoRA can target inner linear layers.
  - Tried device maps (`auto`, `{"":0}`, `None`) with/without `max_memory`, and disabled `llm_int8_enable_fp32_cpu_offload`.
  - Adjusted `TrainingArguments` to remove deprecated `overwrite_output_dir`.
- Current blocker: need either (a) bitsandbytes multi-backend build that permits CPU offload training on Windows, or (b) a larger GPU to keep the 4-bit Gemma 4B model fully resident. No `run_metadata.json` with `status=completed` exists yet.
- `2026-04-07 11:27:28 -05:00` - Evaluated AWS EC2 as a Phase 2 escape path. Conclusion: yes, this training can move to EC2 and is likely the most pragmatic unblock.
- Supporting rationale:
  - The active base model `google/gemma-4-E4B-it` is listed by the Hugging Face model card as `4.5B effective (8B with embeddings)`, which explains why the local 8 GB RTX 2070 is failing even with 4-bit QLoRA.
  - AWS single-GPU candidates with materially more VRAM are available:
    - `g5.xlarge` - 1x NVIDIA A10G, 22 GiB VRAM
    - `g6.xlarge` - 1x NVIDIA L4, 22 GiB VRAM
    - `g6e.xlarge` - 1x NVIDIA L40S, 44 GiB VRAM
    - `g7e.2xlarge` - 1x NVIDIA RTX PRO 6000, 96 GiB VRAM
- Recommended target for this repo's current Gemma Phase 2 path:
  - Prefer Linux on EC2 rather than Windows.
  - Prefer `g6e.xlarge` as the lowest-risk single-GPU option for 4-bit QLoRA training.
  - Treat `g5.xlarge` / `g6.xlarge` as possible but tighter-memory options that may still require more tuning.
- Execution implication: if local Windows remediation continues to stall, the next practical step is to provision a Linux EC2 GPU host, sync the repo and Hugging Face auth, and rerun Step 2.1 there.
- `2026-04-07 11:46:50 -05:00` - Reviewed the existing AWS operator materials under `E:\Finance\MSQlib`, including `secrets\aws\fryCodeKeyPair1.pem`, `secrets\aws\AWS.md`, `scripts\ec2_train_burst.py`, and `var\review3\reports\ec2_burst_runbook.md`.
- Confirmed local shared-profile readiness at `C:\Users\Badass Gojira\.aws\config` and `C:\Users\Badass Gojira\.aws\credentials` with `profile=default` and `region=us-east-2`.
- Re-verified AWS access from this machine by calling STS through a minimal isolated `boto3.Session(profile_name='default')` helper; result: account `095339215660`, ARN `arn:aws:iam::095339215660:user/codex-ec2-launcher`.
- Noted local tooling caveat: the current `aws.exe` on `PATH` resolves to `D:\aws.exe` and fails before normal CLI execution, so the active Phase 2 plan keeps `--profile default` as the auth contract but allows a boto3-backed fallback for local verification until the CLI binary is corrected.

### Phase 2 Execution Attempt - 2026-04-07

- Step `2.1` completed:
  - Created canonical artifact tree under `E:\AI\rComp\execution_plan_11_5`:
    - `dist\hf_cache`
    - `dist\models`
    - `dist\training`
    - `dist\benchmarks`
    - `kg\reports`
    - `transfer\upload`
    - `transfer\download`
- Step `2.2` completed via documented fallback path:
  - `aws sts get-caller-identity --profile default --region us-east-2` failed because local `aws.exe` is broken (`ModuleNotFoundError: No module named '_socket'`).
  - Installed `boto3` into `D:\AI\rComp\dist\pyuser` with `TMP/TEMP` redirected to `D:\AI\rComp\dist\tmp` to avoid `C:` disk exhaustion.
  - STS fallback succeeded with `boto3.Session(profile_name='default', region_name='us-east-2')`:
    - account `095339215660`
    - ARN `arn:aws:iam::095339215660:user/codex-ec2-launcher`
- Step `2.3` failed due account-level AWS quota/capacity constraints:
  - On-demand launch attempt for `g6e.xlarge` in `us-east-2` failed with:
    - `VcpuLimitExceeded`: current vCPU limit is `0` for the required GPU instance bucket.
  - Additional on-demand probes (`g5.xlarge`, `g6.xlarge`, `g4dn.xlarge`) also failed with the same `VcpuLimitExceeded`/limit `0` class error.
  - Spot probes:
    - `g6e.xlarge` failed with `MaxSpotInstanceCountExceeded`.
    - `g6.xlarge` and `g5.xlarge` in validated subnet `subnet-0bc6f9796246ec3a0` (`us-east-2a`) failed with `InsufficientInstanceCapacity`; AWS response suggests `us-east-2b`/`us-east-2c`.
- Steps `2.4` through `2.7` were not executable because Step `2.3` did not produce a running EC2 host.
- Machine-checkable evidence written to:
  - `E:\AI\rComp\execution_plan_11_5\kg\reports\phase2_ec2_attempt_report_2026-04-07.json`
- Residual-resource check after failed launch attempts:
  - tagged instances: none
  - tagged volumes: none

## Phase 2 Gate Status

- Phase `2` is currently **blocked only by external AWS quota approval** (not complete).
- Blocking condition:
  - the EC2 quota `Running On-Demand G and VT instances` is still `0` for the current account context in `us-east-2`.
- Wait-state note:
  - AWS auth, subnet/security-group/key-pair validation, and the EC2 launch preflight are all green.
  - Do not change credential wiring, profiles, key pairs, or subnet/security-group logic; wait for AWS support to approve the quota and then rerun Step `2.3`.

### Phase 2 Re-Execution Attempt - 2026-04-07

- Step `2.1` rerun (`2026-04-07 14:03:26 -05:00`):
  - Recreated/confirmed canonical artifact tree under
    `E:\AI\rComp\execution_plan_11_5`.
- Step `2.2` rerun:
  - `aws sts get-caller-identity --profile default --region us-east-2`
    still fails because local `aws.exe` is broken (`ModuleNotFoundError:
    No module named '_socket'`).
  - boto3 fallback still succeeds and confirms identity:
    `arn:aws:iam::095339215660:user/codex-ec2-launcher`.
- Step `2.2a` (new preflight gate script) executed:
  - command: `py -3 scripts/training/ec2_phase2_preflight.py ...`
  - report:
    `E:\AI\rComp\execution_plan_11_5\kg\reports\phase2_ec2_preflight_latest.json`
  - status: `ready_for_launch_attempt`
  - auth_status: `ok`
  - quota_status: `not_checked`
  - check summary:
    - STS identity: pass
    - subnet/security-group/key pair/AMI resolution: pass
    - instance offering (`g6e.xlarge` in `us-east-2a`): pass
    - service-quotas read: warn (`AccessDeniedException` on
      `servicequotas:ListServiceQuotas`)
- Step `2.3` rerun attempt:
  - launch report:
    `E:\AI\rComp\execution_plan_11_5\kg\reports\phase2_step23_launch_attempt_latest.json`
  - result: failed with `VcpuLimitExceeded` (GPU vCPU bucket limit is `0`)
  - residual check after attempt:
    - active tagged instances: `0`
    - tagged volumes: `0`
- Net result:
  - Phase `2` remains blocked by external AWS quota approval only.
  - The launch-attempt harness terminated cleanly with zero residual tagged
    instances and volumes after the failed launch path.

### Immediate Rerun After Quota Approval

- Re-run command block:

```powershell
aws ec2 run-instances --profile default --region us-east-2 --image-id <amazon-linux-2023-ami> --instance-type g6e.xlarge --key-name fryCodeKeyPair1 --subnet-id <validated-subnet-id> --security-group-ids <validated-security-group-id> --block-device-mappings "[{\"DeviceName\":\"/dev/xvda\",\"Ebs\":{\"VolumeSize\":300,\"VolumeType\":\"gp3\",\"DeleteOnTermination\":true}}]" --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=gemma4-e4b-ear-phase2}]"
```

- Immediate post-approval rules:
  - if the launch succeeds, capture the instance id and continue directly to Steps `2.4` through `2.7`
  - if anything fails after launch, terminate the instance first and verify zero residual tagged instances and volumes before retrying
