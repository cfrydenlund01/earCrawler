# Execution Plan 11.5

Prepared: April 7, 2026
Status: Step 0 and Phase 1 complete; Phase 2 waiting only on external AWS GPU quota approval as of 2026-04-07

Source guidance:

- `docs/production_beta_readiness_review_2026-03-25.md`
- `docs/kg_quarantine_exit_gate.md`
- `docs/kg_unquarantine_plan.md`
- `docs/model_training_surface_adr.md`
- `docs/model_training_contract.md`
- `docs/model_training_first_pass.md`
- `docs/local_adapter_release_evidence.md`
- `docs/ops/release_process.md`
- `docs/ops/windows_single_host_operator.md`

## Purpose

This document keeps the same production-readiness goal as Execution Plan 11.5,
but resets execution to Step 0 for a model-baseline switch.

The finish line is:

1. release evidence is trustworthy,
2. supported Windows single-host deployment is reproducible,
3. corpus -> retrieval -> KG -> API path is current and validated,
4. KG-backed runtime features are either evidenced or explicitly out of scope,
5. the local-adapter path is evidence-backed with a real Gemma 4B-class QLoRA
   candidate (or deliberately remains non-release),
6. one final production decision can be made from current artifacts.

## Active Model Baseline (Hard Requirement)

- Base model ID: `google/gemma-4-E4B-it`
- Family target: Google Gemma 4B-class baseline
- Fine-tuning mode: QLoRA (`--use-4bit` + `--require-qlora-4bit`)
- Training run ID prefix: `gemma4-e4b-ear-<yyyy-mm-dd>-...`
- Benchmark run ID prefix: `benchmark_gemma4-e4b-ear-...`
- Active execution docs, active logs, active config, and active runtime env vars
  must not contain hard-coded legacy model IDs.

## Execution Rules

- Start from Step 0. Do not skip to later phases.
- Do not start a later phase until the current phase gate passes.
- Every completed step must leave machine-checkable evidence under `dist/`,
  `kg/reports/`, or this plan log.
- If a gate fails, execute the contingency in that phase before proceeding.

## Execution Storage Rules

- Canonical large-artifact root for this plan: `E:\AI\rComp\execution_plan_11_5`
- `HF_HOME`, model cache, prepared packages, training runs, smoke outputs,
  benchmark outputs, candidate bundles, upload/download tarballs, and other
  high-volume results must live under that `E:\` root.
- If repo-relative commands still refer to `dist/` or `kg/reports/`, resolve
  them to the `E:\` root via absolute paths or filesystem indirection. Do not
  keep duplicate large copies on `D:\AI\rComp`.
- EC2 training may use only short-lived instance storage or
  delete-on-termination EBS. After artifacts are downloaded back to `E:\`,
  AWS retained storage must be zero: no running or stopped instance, no
  detached volume, no snapshot, no AMI, no S3 object, and no remote cache.

## Step 0 - Gemma Switch Reset (Start Here)

Goal: make the workspace and plan clean for Gemma 4B-class download and
training.

### Step 0.1 - Reset Active Tracking And Identity
Explanation: reset the active execution trail so current progress starts with
Gemma-only identifiers.

Type: `Code`

```powershell
rg -n -S "google/gemma-4-E4B-it|gemma4-e4b-ear|benchmark_gemma4-e4b-ear" docs/ExecutionPlan11.5.md docs/ExecutionPlan11.5_log.md docs/Archive
```

Expected evidence:

- zero legacy hard-coded model identifiers in active execution docs after edits
- `docs/ExecutionPlan11.5_log.md` begins with this reset

### Step 0.2 - Toolchain Preflight For Gemma 4B-Class Loading
Explanation: verify the local Python environment can resolve Gemma 4 config and
that training dependencies are present before attempting full weights download.

Type: `Code`

```powershell
py -3 -m pip show transformers tokenizers accelerate peft bitsandbytes huggingface_hub
py -3 -c "from transformers import AutoConfig; AutoConfig.from_pretrained('google/gemma-4-E4B-it'); print('gemma-config-ok')"
```

Expected evidence:

- dependency versions are visible in console/log
- Gemma config resolution succeeds with `gemma-config-ok`

### Step 0.3 - Authenticated Download Readiness And Cache Location
Explanation: establish deterministic model download location and verify
authenticated access.

Type: `Code`

```powershell
$env:HF_HOME = "E:\AI\rComp\execution_plan_11_5\dist\hf_cache"
$env:HUGGINGFACE_HUB_CACHE = "$env:HF_HOME\hub"
huggingface-cli whoami
huggingface-cli download google/gemma-4-E4B-it --local-dir E:\AI\rComp\execution_plan_11_5\dist\models\gemma-4-e4b-it --resume-download
```

Expected evidence:

- authenticated Hugging Face identity is confirmed
- Gemma model files begin populating
  `E:\AI\rComp\execution_plan_11_5\dist\models\gemma-4-e4b-it`

### Step 0.4 - Build The Active Training Config
Explanation: produce one execution-ready config bound to Gemma 4B-class base
model and approved corpus inputs.

Type: `Prompt`

Model: `GPT-5.3-Codex`
Reasoning: `high`

Prompt:
```text
Use config/training_first_pass.example.json, config/training_input_contract.example.json, docs/model_training_contract.md, and the latest Phase 3 artifact index as governing context. Create the smallest non-placeholder execution-ready training config at dist/training/current_training_config.json for a real first-pass candidate using google/gemma-4-E4B-it and current approved snapshot/corpus values. Preserve the rule that eval and benchmark datasets remain excluded from training inputs. Add/retain validators so placeholder snapshot fields cannot ship.
```

Phase 0 gate:

- Step 0.1 through Step 0.4 are complete
- Active plan/log/config only reference the Gemma 4B-class baseline
- model download path and run-id naming are ready for training

Contingency if gate fails:

- do not start training; resolve auth/toolchain/config blockers first

## Phase 1 - Prepare And Validate Training Package

Goal: produce a valid, non-placeholder training package before GPU-heavy runs.

### Step 1.1 - Prepare-Only Packaging
Type: `Code`

```powershell
py scripts/training/run_phase5_finetune.py --config dist/training/current_training_config.json --prepare-only
```

### Step 1.2 - Validate Prepared Package Metadata
Type: `Code`

```powershell
py -3 -m pytest -q tests/training
```

Expected evidence:

- `dist/training/<run_id>/run_config.json` shows `base_model=google/gemma-4-E4B-it`
- package metadata is complete and validator checks pass

Phase 1 gate:

- prepare-only run passes
- package metadata is valid and complete

## Phase 2 - Execute First Gemma 4B-Class Training Candidate On EC2

Goal: run the first real QLoRA candidate on Linux EC2 because the local Windows
GPU path is blocked by VRAM and offload limits.

EC2 execution constraints:

- target instance: `g6e.xlarge`
- region: `us-east-2`
- OS: Amazon Linux 2023
- GPU shape: `1x NVIDIA L40S, 44 GiB VRAM`
- storage: one delete-on-termination gp3 root/data volume sized only for the
  run; no persistent AWS storage after completion
- AWS auth path: local shared `default` profile
- operator materials already reviewed and available under `E:\Finance`:
  `E:\Finance\MSQlib\secrets\aws\fryCodeKeyPair1.pem`,
  `E:\Finance\MSQlib\secrets\aws\AWS.md`,
  `E:\Finance\MSQlib\var\review3\reports\ec2_burst_runbook.md`, and prior EC2
  launch state under `E:\Finance\MSQlib\var\review3\state\ec2_burst\`
- current readiness confirmation: the `default` profile resolves in
  `C:\Users\Badass Gojira\.aws\config` and `.aws\credentials`, and STS caller
  identity succeeds for `us-east-2`
- Current wait-state: AWS auth and EC2 preflight are green; the only open gate
  is external approval for the EC2 quota `Running On-Demand G and VT instances`
  in `us-east-2`.

### Step 2.1 - Establish The E Drive Artifact Root
Type: `Code`

```powershell
$planRoot = "E:\AI\rComp\execution_plan_11_5"
New-Item -ItemType Directory -Force -Path `
  "$planRoot\dist\hf_cache", `
  "$planRoot\dist\models", `
  "$planRoot\dist\training", `
  "$planRoot\dist\benchmarks", `
  "$planRoot\kg\reports", `
  "$planRoot\transfer\upload", `
  "$planRoot\transfer\download" | Out-Null
```

Expected evidence:

- the canonical execution artifact tree exists on `E:\`
- all later large artifacts have a single approved destination

### Step 2.2 - Confirm AWS Authentication And Operator Inputs
Type: `Code`

```powershell
aws sts get-caller-identity --profile default --region us-east-2
```

Expected evidence:

- STS resolves the active caller identity for the `default` profile
- the selected subnet, security group, key pair, and PEM path are taken from
  the validated operator materials under `E:\Finance`

Note:

- If the local `aws.exe` remains unusable, run the same check through a minimal
  `boto3.Session(profile_name='default')` helper rather than changing
  credentials or creating a second profile.

### Step 2.2a - Run EC2 Launch Preflight Gate
Type: `Code`

```powershell
$env:PYTHONUSERBASE="D:\AI\rComp\dist\pyuser"
py -3 scripts/training/ec2_phase2_preflight.py --profile default --region us-east-2 --instance-type g6e.xlarge --subnet-id <validated-subnet-id> --security-group-id <validated-security-group-id> --key-name fryCodeKeyPair1 --report-path E:\AI\rComp\execution_plan_11_5\kg\reports\phase2_ec2_preflight_latest.json
```

Expected evidence:

- `E:\AI\rComp\execution_plan_11_5\kg\reports\phase2_ec2_preflight_latest.json`
  exists and is machine-readable
- status is `ready_for_launch_attempt` before Step `2.3` is attempted
- if status is `blocked`, record exact blocking checks in
  `docs/ExecutionPlan11.5_log.md` and resolve them before rerunning Step `2.3`

### Step 2.3 - Provision The Short-Lived EC2 Training Host
Type: `Code`

```powershell
aws ec2 run-instances `
  --profile default `
  --region us-east-2 `
  --image-id <amazon-linux-2023-ami> `
  --instance-type g6e.xlarge `
  --key-name fryCodeKeyPair1 `
  --subnet-id <validated-subnet-id> `
  --security-group-ids <validated-security-group-id> `
  --block-device-mappings "[{\"DeviceName\":\"/dev/xvda\",\"Ebs\":{\"VolumeSize\":300,\"VolumeType\":\"gp3\",\"DeleteOnTermination\":true}}]" `
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=gemma4-e4b-ear-phase2}]"
```

Expected evidence:

- one `g6e.xlarge` Linux host is running in `us-east-2`
- the attached volume is delete-on-termination
- no additional persistent AWS storage is provisioned for the run

### Step 2.4 - Stage Only The Minimum Training Inputs
Type: `Code`

```powershell
tar -czf E:\AI\rComp\execution_plan_11_5\transfer\upload\gemma4-phase2-inputs.tgz `
  config\training_first_pass.example.json `
  config\training_input_contract.example.json `
  dist\training\current_training_config.json `
  data\faiss\retrieval_corpus.jsonl `
  data\faiss\index.meta.json `
  snapshots\offline\ecfr_current_20260210_1627_parts_736_740_742_744_746\manifest.json `
  scripts\training
scp -i E:\Finance\MSQlib\secrets\aws\fryCodeKeyPair1.pem E:\AI\rComp\execution_plan_11_5\transfer\upload\gemma4-phase2-inputs.tgz ec2-user@<public-ip>:/home/ec2-user/
```

Expected evidence:

- the upload bundle exists under `E:\AI\rComp\execution_plan_11_5\transfer\upload`
- only repo code, config, manifests, and approved corpus inputs are uploaded
- do not upload the unfine-tuned base model from local storage; download the
  base model directly on EC2 with authenticated Hugging Face access

### Step 2.5 - Bootstrap The EC2 Host And Run QLoRA Training
Type: `Code`

```powershell
ssh -i E:\Finance\MSQlib\secrets\aws\fryCodeKeyPair1.pem ec2-user@<public-ip> @'
set -euo pipefail
mkdir -p /mnt/gemma-phase2/{hf_cache,training}
tar -xzf /home/ec2-user/gemma4-phase2-inputs.tgz -C /home/ec2-user
export HF_HOME=/mnt/gemma-phase2/hf_cache
export HUGGINGFACE_HUB_CACHE=$HF_HOME/hub
cd /home/ec2-user/rComp
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-gpu.txt
huggingface-cli whoami
python scripts/training/run_phase5_finetune.py --config dist/training/current_training_config.json --use-4bit --require-qlora-4bit
'@
```

Expected evidence:

- the remote host downloads `google/gemma-4-E4B-it` directly into remote
  transient storage rather than receiving a copied local base-model tarball
- training completes on the EC2 GPU host
- remote artifacts exist before download under the remote training root

### Step 2.6 - Download Artifacts Back To E And Confirm Completion
Type: `Code`

```powershell
scp -i E:\Finance\MSQlib\secrets\aws\fryCodeKeyPair1.pem -r ec2-user@<public-ip>:/mnt/gemma-phase2/training/<run_id> E:\AI\rComp\execution_plan_11_5\dist\training\
py scripts/training/inference_smoke.py --base-model google/gemma-4-E4B-it --adapter-dir E:\AI\rComp\execution_plan_11_5\dist\training\<run_id>\adapter --out E:\AI\rComp\execution_plan_11_5\dist\training\<run_id>\inference_smoke.json
```

Expected evidence:

- `E:\AI\rComp\execution_plan_11_5\dist\training\<run_id>\run_metadata.json`
  exists with `status=completed`
- the adapter, run metadata, and smoke artifact exist on `E:\`
- no canonical training result is left only on the EC2 host

### Step 2.7 - Terminate The EC2 Host And Verify Zero AWS Residual Storage
Type: `Code`

```powershell
aws ec2 terminate-instances --profile default --region us-east-2 --instance-ids <instance-id>
aws ec2 wait instance-terminated --profile default --region us-east-2 --instance-ids <instance-id>
```

Expected evidence:

- the training instance is terminated
- its delete-on-termination volume is gone with the instance
- there are no retained snapshots, stopped instances, detached volumes, or
  copied training artifacts left in AWS for this run

Phase 2 gate:

- `E:\AI\rComp\execution_plan_11_5\dist\training\<run_id>\run_metadata.json`
  exists with `status=completed`
- smoke artifact exists and is valid
- the EC2 instance used for training is terminated
- AWS retained storage for the run is zero

Contingency if gate fails:

- if EC2 launch fails with `VcpuLimitExceeded` or spot quota/capacity errors,
  do not continue to Steps 2.4-2.7; wait for AWS support to approve the
  `Running On-Demand G and VT instances` quota for `us-east-2`, then rerun
  Step `2.3` immediately.

### Immediate Rerun After Quota Approval
Type: `Code`

```powershell
aws ec2 run-instances `
  --profile default `
  --region us-east-2 `
  --image-id <amazon-linux-2023-ami> `
  --instance-type g6e.xlarge `
  --key-name fryCodeKeyPair1 `
  --subnet-id <validated-subnet-id> `
  --security-group-ids <validated-security-group-id> `
  --block-device-mappings "[{\"DeviceName\":\"/dev/xvda\",\"Ebs\":{\"VolumeSize\":300,\"VolumeType\":\"gp3\",\"DeleteOnTermination\":true}}]" `
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=gemma4-e4b-ear-phase2}]"
```

Teardown safety note:

- if this rerun ever succeeds and later steps fail, terminate the instance
  immediately before any retry and confirm zero residual tagged instances and
  volumes before reattempting

## Phase 3 - Runtime Smoke And Benchmark Evidence

Goal: prove the candidate works in the optional local-adapter runtime path.

### Step 3.1 - Local Adapter Runtime Smoke
Type: `Code`

```powershell
pwsh scripts/local_adapter_smoke.ps1 -RunDir E:\AI\rComp\execution_plan_11_5\dist\training\<run_id>
```

### Step 3.2 - Benchmark Preflight
Type: `Code`

```powershell
py -m scripts.eval.run_local_adapter_benchmark --run-dir E:\AI\rComp\execution_plan_11_5\dist\training\<run_id> --manifest eval/manifest.json --dataset-id ear_compliance.v2 --max-items 5 --run-id benchmark_gemma4-e4b-ear-<run_tag>_preflight --smoke-report E:\AI\rComp\execution_plan_11_5\kg\reports\local-adapter-smoke.json --timeout-seconds 120 --max-consecutive-transport-failures 3 --overwrite
```

### Step 3.3 - Primary Benchmark Run
Type: `Code`

```powershell
py -m scripts.eval.run_local_adapter_benchmark --run-dir E:\AI\rComp\execution_plan_11_5\dist\training\<run_id> --manifest eval/manifest.json --dataset-id ear_compliance.v2 --dataset-id entity_obligations.v2 --dataset-id unanswerable.v2 --run-id benchmark_gemma4-e4b-ear-<run_tag>_primary --smoke-report E:\AI\rComp\execution_plan_11_5\kg\reports\local-adapter-smoke.json --timeout-seconds 120 --local-adapter-warmup-timeout-seconds 240 --max-consecutive-transport-failures 3 --require-authenticated-api --require-api-key-label benchmark --overwrite
```

Phase 3 gate:

- smoke passes
- benchmark bundle exists and contains preconditions + summary

## Phase 4 - Candidate Validation And Release Decision Inputs

Goal: produce one machine-checkable decision artifact for the candidate.

### Step 4.1 - Validate Local Adapter Release Bundle
Type: `Code`

```powershell
py -m scripts.eval.validate_local_adapter_release_bundle --run-dir E:\AI\rComp\execution_plan_11_5\dist\training\<run_id> --benchmark-summary E:\AI\rComp\execution_plan_11_5\dist\benchmarks\benchmark_gemma4-e4b-ear-<run_tag>_primary\benchmark_summary.json --smoke-report E:\AI\rComp\execution_plan_11_5\kg\reports\local-adapter-smoke.json
```

### Step 4.2 - Build Reviewable Candidate Bundle
Type: `Code`

```powershell
py -m scripts.eval.build_local_adapter_candidate_bundle --run-dir E:\AI\rComp\execution_plan_11_5\dist\training\<run_id> --benchmark-summary E:\AI\rComp\execution_plan_11_5\dist\benchmarks\benchmark_gemma4-e4b-ear-<run_tag>_primary\benchmark_summary.json --smoke-report E:\AI\rComp\execution_plan_11_5\kg\reports\local-adapter-smoke.json --overwrite
```

### Step 4.3 - Update Capability Decision Inputs
Type: `Prompt`

Model: `GPT-5.4`
Reasoning: `high`

Prompt:
```text
Use docs/local_adapter_release_evidence.md, docs/answer_generation_posture.md, the new Gemma candidate bundle, and current runtime/operator docs. Refresh the dated capability decision inputs so they reflect only current Gemma run evidence and clearly state whether local-adapter serving remains Optional or is ready for formal promotion review.
```

Phase 4 gate:

- candidate bundle is reviewable
- decision outcome is explicit (`keep_optional`, `reject_candidate`, or `ready_for_formal_promotion_review`)

## Phase 5 - Post-Run Consolidation And Cleanup

Goal: keep only durable evidence while removing single-use local and AWS
artifacts that no longer justify storage or cost.

### Step 5.1 - Freeze The Retained Artifact Set On E
Type: `Code`

```powershell
Get-ChildItem -Recurse E:\AI\rComp\execution_plan_11_5\dist\training\<run_id>
Get-ChildItem -Recurse E:\AI\rComp\execution_plan_11_5\dist\benchmarks\benchmark_gemma4-e4b-ear-<run_tag>_primary
```

Retain only:

- final adapter directory
- `run_config.json`, `run_metadata.json`, `inference_smoke.json`
- benchmark summaries and supporting reports needed for release evidence
- the final candidate bundle and decision artifacts

### Step 5.2 - Delete Single-Use Local Files
Type: `Code`

```powershell
Remove-Item E:\AI\rComp\execution_plan_11_5\transfer -Recurse -Force
```

After Phase 4 evidence is accepted and no immediate rerun window remains, also
delete single-use local artifacts such as:

- upload and download tarballs
- temporary bootstrap installers and ad hoc EC2 helper environments
- redundant local copies of the unfine-tuned base model
- any stale or duplicate prepared-package outputs that are not part of the
  retained artifact set

### Step 5.3 - Verify Zero AWS Residual Storage
Type: `Code`

```powershell
aws ec2 describe-instances --profile default --region us-east-2 --filters "Name=tag:Name,Values=gemma4-e4b-ear-phase2"
aws ec2 describe-volumes --profile default --region us-east-2 --filters "Name=status,Values=available,in-use"
aws ec2 describe-snapshots --profile default --region us-east-2 --owner-ids self
```

Expected evidence:

- no EC2 instance from this run remains running or stopped
- no detached EBS volume or snapshot remains for the training run
- no copied model, cache, or result artifact remains stored anywhere in AWS

Phase 5 gate:

- only durable final evidence remains on `E:\`
- single-use local artifacts are removed
- AWS retained storage is zero after training and artifact download

## Completion Condition

Execution Plan 11.5 is complete when:

1. Step 0 through Phase 5 are complete with machine-checkable artifacts,
2. active execution docs/logs/config contain only Gemma 4B-class model IDs,
3. canonical model, training, and benchmark artifacts are stored on `E:\` and
   not duplicated unnecessarily on the local workspace drive,
4. EC2-based Gemma download + training + benchmark reruns are documented and
   repeatable,
5. final production decision inputs are current,
6. AWS retained storage for the training run is zero.

## Recommended Execution Order

1. Finish Step 0 completely before any training command.
2. Finish Phase 1 before running full training.
3. Finish Phase 2 before any runtime or benchmark claim.
4. Finish Phase 3 before any capability or production decision input updates.
5. Finish Phase 4 before post-run cleanup.
6. Finish Phase 5 before final production-readiness synthesis.

