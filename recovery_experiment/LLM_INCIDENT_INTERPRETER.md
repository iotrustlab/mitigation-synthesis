# Local LLM Incident Interpretation

## Scope and status

Qwen 3.5-9B is the **initial development model** for the Dr.ICS
`LLMIncidentInterpreter`. It is not a trusted component and it is not the only
supported model. The implementation boundary is deliberately:

```text
IncidentEvidence
      |
      v
LLMIncidentInterpreter
      |
      v
OpenAI-compatible backend ---- DRICS_LLM_MODEL
      |
      v
local model server (initially Qwen 3.5-9B)
      |
      v
CandidateRecoveryContext
      |
      v
unchanged trusted grounding and formal recovery pipeline
```

Changing `DRICS_LLM_MODEL`, the endpoint, or the server must not require a
change to `CandidateRecoveryContext`, trusted grounding, formal-model
construction, certificates, service checks, cost ranking, or recovery
selection. Qwen-specific behavior belongs only in serving/setup configuration.

The login host's NVIDIA GeForce GT 1030 has only 2 GiB of VRAM and is
explicitly unsuitable. On 2026-09-26, the managed workflow started the pinned
model successfully on a CHPC RTX A6000 and reached the OpenAI-compatible API,
but the first smoke request failed before generation because both
structured-output backends in the installed vLLM 0.27.0 image reject the
unchanged schema's `uniqueItems` keyword. The reviewed serving adapter then
allowed one new smoke to generate canonical-schema-valid JSON. That response
failed closed at provenance validation, before grounding. Both first attempts
are preserved; the canonical schema was not weakened and the 27-case baseline
was not run.

## Verified official artifact

The initial artifact is the official, post-trained chat model
[`Qwen/Qwen3.5-9B`](https://huggingface.co/Qwen/Qwen3.5-9B), pinned to commit:

```text
c202236235762e1c871ad0ccb60c8ee5ba337b9a
```

The immutable repository view is
[`Qwen/Qwen3.5-9B@c202236...`](https://huggingface.co/Qwen/Qwen3.5-9B/tree/c202236235762e1c871ad0ccb60c8ee5ba337b9a).
This repository is public and ungated and carries the
[`Apache-2.0` license](https://huggingface.co/Qwen/Qwen3.5-9B/blob/c202236235762e1c871ad0ccb60c8ee5ba337b9a/LICENSE).
It is the interactive/chat artifact even though its name has no `-Instruct`
suffix. `Qwen/Qwen3.5-9B-Base` is a separate base model and is not this
baseline.

The pinned artifact has these properties:

- Official size name: 9B; exact tensor parameter count: 9,653,104,368.
- Weight representation: four BF16 safetensor shards totaling
  19,306,310,880 bytes (about 17.98 GiB), described by the pinned
  [`model.safetensors.index.json`](https://huggingface.co/Qwen/Qwen3.5-9B/blob/c202236235762e1c871ad0ccb60c8ee5ba337b9a/model.safetensors.index.json).
- Architecture: `Qwen3_5ForConditionalGeneration`, a dense multimodal causal
  model with a vision encoder, 32 language-model layers, and hybrid gated
  DeltaNet/full gated-attention blocks. Dr.ICS uses only the language path.
- Native context: 262,144 tokens. The initial Dr.ICS server deliberately limits
  the operational context to 16,384 tokens and does not enable YaRN extension.
- Tokenization: the packaged Qwen tokenizer/chat template (`Qwen2Tokenizer` in
  the tokenizer metadata), EOS `<|im_end|>`, padding `<|endoftext|>`, and no
  added BOS token. Direct Transformers use should load the matching
  `AutoProcessor`; the normal Dr.ICS path delegates tokenization to vLLM.
- Chat/instruction use: supported by the packaged chat template. Thinking is
  disabled for this extraction task so the response contains only the schema
  object, not reasoning prose.

The exact architecture and context settings are recorded in the pinned
[`config.json`](https://huggingface.co/Qwen/Qwen3.5-9B/blob/c202236235762e1c871ad0ccb60c8ee5ba337b9a/config.json),
and tokenizer behavior is recorded in the pinned
[`tokenizer_config.json`](https://huggingface.co/Qwen/Qwen3.5-9B/blob/c202236235762e1c871ad0ccb60c8ee5ba337b9a/tokenizer_config.json).
The [official model card](https://huggingface.co/Qwen/Qwen3.5-9B/blob/c202236235762e1c871ad0ccb60c8ee5ba337b9a/README.md)
is the primary usage reference.

### Runtime compatibility

The official direct-Transformers example requests a current Transformers build
from source and does not state a numeric minimum. Released
[Transformers 5.17 documentation](https://huggingface.co/docs/transformers/v5.17.0/model_doc/qwen3_5)
includes the Qwen 3.5 classes; 5.17.0 is therefore the initial known-compatible
release to pin if a direct-Transformers auxiliary environment is later needed,
subject to an actual compatibility test. Direct Transformers inference is not
the baseline serving path, so Transformers, PyTorch, and CUDA packages must not
be installed in the CLEO environment.

The selected server is vLLM. The
[official vLLM Qwen 3.5-9B recipe](https://github.com/vllm-project/recipes/blob/main/models/Qwen/Qwen3.5-9B.yaml)
requires vLLM 0.17.0 or newer and uses language-model-only serving. vLLM's
[structured-output API](https://docs.vllm.ai/en/latest/features/structured_outputs/)
supports OpenAI-compatible `response_format` JSON Schema constraints. This
constrains generation, but it does not replace Dr.ICS's local schema,
provenance, vocabulary, and evidence-ID validation.

For a separately built serving environment, the initial version candidate is
the current stable [vLLM 0.30.0 release](https://github.com/vllm-project/vllm/releases/tag/v0.30.0),
pinned and validated rather than installed into CLEO. On CHPC, the centrally
managed container is preferred to a duplicate local install.

On CHPC, `module load vllm/current` exposes a shell function named
`vllm_serve`; it launches the centrally managed CUDA Apptainer image with GPU
passthrough rather than installing a host `vllm` executable. Current image
inspection reported vLLM 0.27, which satisfies the 0.17.0 minimum. The launcher
identifies the selected runtime, and the evaluator requires and records the
server `/version` response because a `current` module can change independently
of this repository.

### GPU and quantization decision

The four BF16 shards occupy about 18 GiB before runtime allocations. FP16 has
the same two-byte-per-parameter storage class, although the official recipe and
this baseline use BF16. The official vLLM recipe identifies roughly 22 GB of
GPU memory as the lower bound; a 24 GB GPU is the practical single-GPU starting
point for this baseline. Runtime KV cache needs vary with context and
concurrency, which is why Dr.ICS uses a 16,384-token operational limit rather
than the full native context.

The official Qwen organization does not publish a quantized 9B artifact for
this pinned model. Community quantizations are different derived artifacts and
must not silently replace the BF16 baseline. A later quantized experiment must
name and pin its own repository and revision, validate compatibility, record
the quantization method and memory behavior, and preserve its results under a
different experiment identity. No quantization, LoRA, QLoRA, supervised
fine-tuning, preference optimization, or domain adaptation is part of this
baseline. Pure weight-size arithmetic would put 8-bit and 4-bit copies near
9 GiB and 4.5 GiB respectively before scales, runtime workspace, activations,
and KV cache; those figures are not practical VRAM guarantees. No community
quantized derivative has been accepted or memory-validated for this baseline.

## Separation from CLEO

Keep the two runtime stacks independent:

```text
CLEO environment                 LLM serving environment
----------------                 -----------------------
CLEO                             vLLM
Z3                              PyTorch/CUDA
KeYmaera X                      model/tokenizer runtime
formal-verification packages    Qwen weights
```

The CHPC vLLM module/container is the preferred LLM environment. A local
fallback, if it is ever needed, belongs below `.external/llm/`, which is ignored
by Git. Do not install vLLM, Transformers, PyTorch, CUDA packages, or Qwen
dependencies into `.external/cleo/.venv` or modify the reviewed formal
artifacts for model-serving convenience.

The LLM pipeline does not invoke CLEO online. It reuses the existing local
formal assessment and reviewed certificate-coverage logic. An LLM response is
never a proof, a certificate, or authorization to actuate anything.

## Storage and download

Weights must live outside this Git repository. The group Oak filesystem that
contains the repository had about 10 TiB free when inspected, whereas the
personal home allocation was nearly full. The recommended configurable layout
is therefore a sibling on group storage:

```text
/uufs/chpc.utah.edu/common/home/garcia-group1/drics-llm/
    models/
    cache/
```

The scripts derive the portable equivalent from the repository parent rather
than embedding that absolute path. Override it when cluster policy requires a
different volume:

```bash
export DRICS_MODEL_DIR="$(cd .. && pwd)/drics-llm/models"
export HF_HOME="$(cd .. && pwd)/drics-llm/cache"
```

Do not leave `HF_HOME` unset on this machine: Hugging Face would otherwise use
the nearly full personal-home cache. Do not put weights under
`recovery_experiment/`, `.git/`, or another tracked source directory.

Download the pinned official snapshot with:

```bash
scripts/llm/download_qwen35_9b.sh
```

The downloader checks the target filesystem's free space before transfer,
uses Hugging Face's resumable snapshot mechanism, and writes a manifest beside
the completed snapshot. The manifest records the official model ID, requested
revision, resolved commit, UTC download time, and copies/hashes of model and
tokenizer configuration. Re-running an interrupted download resumes available
objects. Credentials, if ever needed, come from the standard Hugging Face
credential mechanism or `HF_TOKEN`; the script never writes or prints a token.

For this checkout, the pinned snapshot was downloaded on 2026-09-26 to:

```text
/uufs/chpc.utah.edu/common/home/garcia-group1/drics-llm/models/
  Qwen--Qwen3.5-9B/c202236235762e1c871ad0ccb60c8ee5ba337b9a/
```

Its `DRICS_MODEL_MANIFEST.json` resolves the requested commit to the same hash,
records 16 source files totaling 19,329,393,661 bytes, and records the four
tensor shards totaling 19,306,310,880 bytes. The path is an observed deployment
choice, not a source-code default; scripts still derive a portable sibling path
or honor `DRICS_MODEL_DIR`.

## Initial serving configuration

The reproducible development baseline is:

```text
model ID                 Qwen/Qwen3.5-9B
model revision           c202236235762e1c871ad0ccb60c8ee5ba337b9a
backend                   vLLM >= 0.17.0, OpenAI-compatible API
weights                   BF16, no quantization
language-only mode        enabled
thinking                  disabled
maximum model context     16384
temperature               0
top_p                     1
seed                      20260926
maximum output tokens     4096
structured output         strict JSON Schema plus local validation
```

These decoding values are an experimental reproducibility configuration for
structured incident extraction. They are not Qwen's general-purpose sampling
recommendation: the official card recommends `temperature=0.7` and `top_p=0.8`
for ordinary non-thinking generation. A fixed seed and greedy-like settings
reduce variability but do not guarantee bit-identical output across hardware,
kernel, backend, or backend-version changes. All of those inputs must therefore
be recorded with each experiment.

The 4,096-token output ceiling accommodates the complete provenance-bearing
schema; the prompt instructs the model to emit JSON only, with no prose or
chain-of-thought. The 16,384-token model context is an operational limit, not a
claim that the model lacks its documented 262,144-token native context.

## Canonical schema, serving schema, and security boundary

The two schemas have deliberately different roles:

- `candidate_response_schema()` in `llm_incident_interpreter.py` produces the
  **canonical CandidateRecoveryContext schema**. It is the authoritative local
  acceptance contract, version `candidate-recovery-context-v1`, with SHA-256
  `7b5237458e64d0aa6b26dbf954a2c4829aae499ba72aeaf33952ec2869fd0e5a`.
- `build_serving_schema()` in `structured_output_schema.py` produces a
  **serving schema** for constrained generation only. For the reviewed vLLM
  auto profile (xgrammar with Guidance fallback), its SHA-256 is
  `3680129007e01223a2b6f2d6eba73d834316434ea04356393c4924535d5bd0e1`.

The canonical schema has 64 `uniqueItems: true` occurrences: the
`evidence_ids`, `sources`, `rule_ids`, and `conflict_evidence_ids` arrays in
each of the 16 candidate claims. vLLM 0.27.0 cannot compile that keyword. The
reviewed serving policy therefore removes only those 64 generation-time
keyword occurrences and records every parent JSON path, keyword, and value.
It does not mutate the canonical object or remove an arbitrary keyword merely
because a backend rejects it. A newly reported unsupported keyword is
`INCOMPATIBLE` until it receives an explicit code review and policy change.

For example, the canonical fragment remains:

```json
{
  "evidence_ids": {
    "type": "array",
    "items": {"type": "string", "minLength": 1},
    "uniqueItems": true
  }
}
```

The vLLM serving copy omits only `uniqueItems` while generating tokens. If a
model consequently returns `["observation-1", "observation-1"]`, JSON parsing
can succeed but the local Draft 2020-12 canonical validator rejects the output
as non-unique. Dr.ICS never deduplicates, repairs, or normalizes it into an
acceptable candidate, and grounding is not called.

The local compatibility preflight runs before allocation/model loading in the
managed workflow and can also be inspected directly:

```bash
.venv/bin/python -m recovery_experiment.llm_incident_evaluation \
  preflight --serving-backend vllm-auto
```

It reports the backend, policy version, canonical and serving hashes, 513 and
449 constraint occurrences respectively, all 64 reviewed removals, zero
unhandled constraints, and `COMPATIBLE_WITH_CLIENT_VALIDATION`. Every live
experiment records the same report plus the actual `/version` response.

A serving-schema success is not a trust decision. Raw output must pass the
full canonical JSON Schema validator, candidate type/vocabulary checks,
evidence-ID and source checks, observed-value binding, and unchanged trusted
grounding before it can enter the formal recovery pipeline. The LLM never
authorizes recovery directly.

## Managed CHPC allocation and experiment workflow

The normal automated path uses the repository's ownership-safe GPU allocator:

```bash
scripts/llm/allocate_gpu.sh --min-vram 32 --wait
scripts/llm/gpu_allocation_status.sh
scripts/llm/run_on_gpu.sh nvidia-smi
```

The verified ordered partition/account pairs are
`soc-gpu-np:soc-gpu-np` followed by
`notchpeak-gpu:notchpeak-gpu`. Override them only with another approved
mapping through `DRICS_GPU_PARTITIONS`. Generic `--gres=gpu:1` is the default;
`--gpu-type` or `DRICS_GPU_GRES` may use an exact GPU type advertised by
current Slurm configuration.

`freegpus` is a Stage-A advisory. Its count can include GPUs on drained,
reserved, or CPU/RAM-blocked nodes and it neither reserves a device nor
establishes its memory. After a job starts, the allocator runs `nvidia-smi`
inside the allocation and accepts it only when every required CUDA-visible GPU
meets the configured memory threshold. Defaults are one GPU, at least 32 GiB
of VRAM per GPU, eight CPUs, 32 GiB of CPU RAM, four hours of walltime, and a
finite 60-second allocation wait. These are policy defaults rather than a
claim that Qwen requires exactly 32 GiB; each is configurable.

Accepted allocation metadata is written atomically under the ignored
`.run/drics-gpu/` directory. A UID- and repository-specific managed marker,
per-job ledger, and allocation lock prevent duplicate submission and ensure
that cleanup cannot target an unrelated Slurm job. A matching running job is
reused only after its owner, marker, node, CPU/RAM, allocation time limit,
remaining-time floor, GPU count, and VRAM are revalidated.

For the complete managed lifecycle, use:

```bash
# Default and explicit safe mode: exactly one smoke case.
scripts/llm/run_qwen_baseline.sh --smoke-only

# Run the immutable 27-case record only when deliberately requested.
scripts/llm/run_qwen_baseline.sh --baseline

# End the retained allocation after the work is complete.
scripts/llm/release_gpu.sh
```

The high-level runner obtains or reuses the allocation, then starts the Qwen
server and evaluator in one foreground Slurm step. They communicate through
`127.0.0.1`; no public compute-node listener or SSH tunnel is required. The
runner waits for `/v1/models`, runs a fresh smoke case, and proceeds to all 27
cases only with `--baseline`. The server runs in its own process group and is
always stopped on success, failure, or interruption. The allocation remains
active unless `--release-gpu` is passed. `stop_qwen_server.sh` can stop only
the exact recorded active server step and does not release the GPU job.

See [`scripts/llm/GPU_ALLOCATION.md`](../scripts/llm/GPU_ALLOCATION.md) for the
full configuration, state, stable stdout, dry-run, and cleanup contracts.

### 2026-09-26 smoke compatibility result

Live allocation validation used job `15842018` in `soc-gpu-np` on `notch501`.
`nvidia-smi` reported one NVIDIA RTX A6000 with 46,068 MiB. vLLM 0.27.0 loaded
the four BF16 shards in text-only mode, exposed `Qwen/Qwen3.5-9B` through
`/v1/models`, and then rejected the unchanged response schema before model
generation:

```text
xgrammar: provided JSON schema contains unsupported features
Guidance fallback: Unimplemented keys: ["uniqueItems"]
```

The diagnostic smoke record is under
`recovery_experiment/results/llm/orchestrated/20260926T072219Z-job15842018-step33-3970453/smoke/`.
It records HTTP 500, no model response, and no execution of grounding or the
formal assessment. The managed server stopped and job `15842018` was released;
the unrelated `vscode-gpu` job was not touched. This is a serving-backend
compatibility result, not permission to change the schema, skip local
validation, or run the full baseline.

### 2026-09-26 serving-adapted smoke result

After the compatibility adapter and its regression tests passed, the managed
workflow allocated job `15844987` in `soc-gpu-np` on `notch368`. The selected
RTX A6000 again reported 46,068 MiB. vLLM 0.27.0 loaded the exact pinned BF16
model and accepted the serving schema: 64 reviewed `uniqueItems` occurrences
were omitted from constrained generation, with zero unhandled constraints.

Exactly one request for `A-immediate-nominal-1` returned valid JSON with
response ID `chatcmpl-ba78b26622139548`, `finish_reason=stop`, 1,264 prompt
tokens, 2,243 completion tokens, and 71.28 seconds client-observed latency. The
full canonical Draft 2020-12 schema validation passed. Provenance validation
then rejected the response because Qwen cited the fabricated ID
`incident_metadata:plant_identity` instead of the supplied
`metadata:plant_identity`. Its `sources` arrays also copied provenance IDs
rather than the source strings bound to those IDs, so the offline audit marked
15 fields unsupported. Nothing was repaired or deduplicated.

The preserved record is under
`recovery_experiment/results/llm/orchestrated/20260926T144714Z-job15844987-step2-1405888/smoke/`.
Its per-case validation block records canonical schema `PASS` and
provenance/binding `FAIL`; `pipeline` is null, proving grounding, formal-model
construction, certificate assessment, service/cost evaluation, and recovery
selection did not execute. Consequently no online CLEO invocation and no
direct LLM recovery authorization occurred. The server stopped, job
`15844987` was released, and no `QWEN_BASELINE_V1` directory was created.

The preserved first-attempt `completion.json` predates a reporting correction:
its `canonical_schema_valid` and `online_cleo_not_invoked` booleans conflate
candidate construction/pipeline execution with those two independent facts.
The per-case staged validation is correct. The reporting logic was corrected
and regression-tested without rewriting or rerunning the first attempt.

## Manual server launch on an allocated GPU node

Never start the model on the GT 1030 login/development host. First obtain a
suitable CHPC GPU allocation, then run on the allocated compute node:

```bash
export DRICS_MODEL_DIR="/path/on/group-or-cluster-storage/drics-llm/models"
export DRICS_LLM_HOST=127.0.0.1
export DRICS_LLM_PORT=8000
export DRICS_LLM_MODEL=Qwen/Qwen3.5-9B
export DRICS_LLM_MAX_MODEL_LEN=16384
export DRICS_LLM_GPU_MEMORY_UTILIZATION=0.90
export DRICS_LLM_TENSOR_PARALLEL_SIZE=1

scripts/llm/start_qwen35_9b_server.sh
```

The launcher loads the separate CHPC vLLM module when available, resolves the
pinned local snapshot, checks visible GPUs and memory, and rejects obviously
insufficient hardware before model loading. It reports the hostname, GPUs,
model/revision, endpoint, context limit, memory utilization, and parallelism.
One suitable GPU is preferred for the 9B baseline; tensor parallelism is not
assumed. Increase `DRICS_LLM_TENSOR_PARALLEL_SIZE` only when the allocation and
an explicitly recorded experiment configuration justify it.

The default bind address is loopback. Binding to a shared network interface is
a deployment/security decision, not a baseline requirement. The API key
variable, if a server is configured to require one, must remain an environment
secret and is never included in reproducibility output.

### Manual Slurm example

Copy and edit `scripts/llm/qwen35_9b.sbatch.example`. Its account,
partition, GPU type, and QoS fields remain placeholders so that the portable
example does not silently assume this user's current CHPC associations. The
managed allocator above is preferred on this checkout. A manual submission is:

```bash
cp scripts/llm/qwen35_9b.sbatch.example /tmp/qwen35_9b.sbatch
# Replace <ACCOUNT>, <GPU_PARTITION>, and <GPU_TYPE>; add an approved QoS only
# if your allocation requires it.
sbatch /tmp/qwen35_9b.sbatch
```

The example prints `hostname` and `nvidia-smi`, loads the server environment,
sets the model location, and launches the OpenAI-compatible service. Do not put
credentials into the copied job script or scheduler log.

### SSH forwarding

If compute-node ports are not directly reachable, leave the server on
`127.0.0.1:<port>` and forward it. With an institution-approved route to the
allocated node, the pattern is:

```bash
ssh -N -L 8000:127.0.0.1:8000 <user>@<allocated-node>
```

If CHPC requires a login-node jump, use the site's approved jump-host form,
for example:

```bash
ssh -N -J <user>@<login-host> \
  -L 8000:127.0.0.1:8000 <user>@<allocated-node>
```

Then point the Dr.ICS process at the local end of the tunnel:

```bash
export DRICS_LLM_BASE_URL=http://127.0.0.1:8000/v1
export DRICS_LLM_MODEL=Qwen/Qwen3.5-9B
```

When the evaluator itself runs on the tunnel client instead of the allocated
GPU node, export `DRICS_LLM_GPU_MODEL` and `DRICS_LLM_GPU_COUNT` from the job's
recorded `nvidia-smi` output. Otherwise automatic hardware discovery would
describe the client GPU rather than the inference GPU. Also preserve the
server's tensor-parallel and context settings in the evaluator environment.

Verify that `GET /v1/models` returns the configured served-model name before
starting an evaluation. The client also records the optional server `/version`
response.

## Untrusted interpretation contract

`LLMIncidentInterpreter` sends only `IncidentEvidence` and the minimum output
schema/vocabulary needed to construct `CandidateRecoveryContext`. The model is
not given gold scenario labels, expected templates, expected formal models,
certificate conditions/results, CLEO results, service outcomes, or expected
recovery decisions. The evaluator joins model results to gold labels only after
generation and validation.

Every response passes local checks even when server-side constrained decoding
succeeds:

1. JSON parsing.
2. Full canonical CandidateRecoveryContext JSON Schema validation using an
   explicit `jsonschema.Draft202012Validator`.
3. Incident-ID, value type, allowed vocabulary, and status validation.
4. Verification that every cited evidence ID exists in the input incident.
5. Verification that cited sources match input evidence and that unknown or
   conflicting claims obey their provenance rules.
6. Observed-value and field/evidence binding validation.
7. Construction of the existing `CandidateRecoveryContext` type.
8. Execution of unchanged trusted grounding, which may reject the candidate.
9. Execution of the unchanged template, formal assessment, certificate,
   service, cost, and final-decision path when grounding succeeds.

The LLM may extract observations and make only the narrowly defined compromise
inference supported by security evidence plus an unauthorized command event.
It cannot establish trusted topology, component trust, recovery authority,
formal safety, certificate applicability, or permission to issue controls. A
schema-valid response can still be false and can still be rejected by
grounding. No model output is sent to an actuator.

## Smoke test

The recommended command obtains or reuses verified hardware, manages server
readiness and cleanup, and runs exactly one existing incident:

```bash
scripts/llm/run_qwen_baseline.sh --smoke-only
```

When operating an already running endpoint manually, the lower-level command
is:

```bash
scripts/llm/smoke_qwen35_9b.sh
```

The wrapper invokes `python -m recovery_experiment.llm_incident_evaluation
smoke` with the documented model, revision, manifest, and decoding defaults;
CLI flags may override the endpoint or output directory. It refuses to
overwrite its default `recovery_experiment/results/llm/QWEN_SMOKE_V1` record.

The smoke result belongs under the ignored, noncanonical experiment-output
tree, not in reviewed proof-record directories. It must preserve the raw model
response and validation trace and explicitly establish:

- endpoint reachability and a model response;
- successful JSON/schema parsing;
- validity of all cited evidence IDs and sources;
- `CandidateRecoveryContext` construction;
- execution of trusted grounding and formal assessment;
- absence of an online CLEO invocation; and
- absence of direct LLM recovery authorization.

A failed smoke test is a compatibility or interpretation result. Do not weaken
the schema, grounding, formal checks, or certificates merely to make it pass.

## Immutable 27-case baseline

Only when the full run is deliberately requested, use the managed command. It
always performs a fresh smoke case before evaluating the unchanged complete
27-case gold dataset:

```bash
scripts/llm/run_qwen_baseline.sh --baseline
```

For a manually managed endpoint with its required successful smoke record, the
lower-level evaluation wrapper remains:

```bash
scripts/llm/baseline_qwen35_9b.sh
```

The baseline wrapper likewise uses the generic evaluator. Its default output
is `recovery_experiment/results/llm/QWEN_BASELINE_V1`, and creation is exclusive:
an existing first-attempt directory is never replaced.

`QWEN_BASELINE_V1` is the first-attempt scientific record. Do not tune the
prompt against individual gold cases before this run and do not overwrite the
directory if performance is poor. Later prompt/schema experiments use new
names such as `prompt-v2`; they do not revise baseline-v1 in place.

The preserved record must contain:

- official model ID and exact resolved revision;
- backend and server version;
- prompt version/hash, candidate-schema version, canonical-schema hash,
  serving-schema hash, serving backend/version, and every removed constraint;
- decoding settings and operational context;
- GPU model/count, tensor parallelism, dtype, and quantization status;
- per-case raw output, parsed candidate, validation result, and latency;
- grounding and downstream pipeline results; and
- aggregate metrics.

Aggregate reporting covers:

- Interpretation: compromised component, attacker capability, physical state,
  resource observations, and timing.
- Provenance: valid references, fabricated IDs, missing support, and unsupported
  claims.
- Grounding: correct acceptance/rejection and false acceptance/rejection.
- Formal consequences: template, formal model, certificate, service contract,
  and final recovery decision.
- Error propagation: interpretation errors with no downstream effect, rejected
  by grounding, or changing the template, formal problem, certificate
  applicability, or final decision.

The deterministic interpreter and all gold labels remain unchanged. This is a
comparison baseline, not a replacement or an optimization pass.

## Completion states

Use exactly one outcome label when handing off this work:

- `READY_FOR_QWEN_BASELINE_V1`: the pinned model completed the smoke and every
  required validation/pipeline check passed; stop before tuning or baseline.
- `QWEN_SMOKE_BLOCKED`: the single smoke failed; report its exact failure layer
  and do not tune, weaken validation, or run the 27-case baseline.

The current outcome is `QWEN_SMOKE_BLOCKED` at `PROVENANCE_FAILURE`. Serving
schema generation and full canonical validation succeeded, but the model cited
a fabricated metadata ID and supplied incorrect ID-to-source bindings.
Grounding and downstream formal/certificate work were not executed.

The current hardware constraint by itself is not permission to use the GT 1030
or substitute a different/quantized model. Run the official pinned BF16 model
on a suitable allocated GPU node, or report the appropriate state above.
