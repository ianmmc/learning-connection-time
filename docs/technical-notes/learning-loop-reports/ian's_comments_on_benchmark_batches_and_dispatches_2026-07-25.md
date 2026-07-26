# Ian's re-anchoring of batches, dispatches, and the type axis — 2026-07-25

> **What this is:** Ian's own statement of intent for the benchmark model, written mid-implementation of
> epic #617 and preserved **verbatim** — his words, unedited, including typos. It is a *primary source*
> for why the type axis exists, not a design spec.
>
> **Why it exists:** it was written to re-anchor the concept while #617 was in flight, and it earned its
> keep immediately — it confirmed the terminus model and the representation-grain keying, and it
> **falsified a shipped assumption** (the benchmark-*batch* terminus turned out to have no enforcement
> for any newly-composed benchmark batch → GitHub **#640**).
>
> **Read this next — two points below were resolved DIFFERENTLY by the end of the same conversation:**
> 1. **Dispatches have TWO types, not three** (`production | benchmark`). A dispatch has no
>    first-run/follow-up notion — that is derivable from a district's dispatch history, and a third
>    value carrying no behavior is the string-equality coupling #617 exists to retire.
> 2. **"Follow-up … more automated by default"** describes *where the decision sits* (gate@5/gate@7
>    authorized the targeting; the composer executes it), **not** a gate setting. `gate_mode` is keyed by
>    gate alone, with no type dimension, and an escalation-composed follow-up still passes gate@1.
>
> Both are recorded in §11.3 of
> `2026-07-25-epic617-benchmark-model-findings.md` (this directory), which is where the conversation
> landed and which carries the evidence. Durable architecture:
> `../PIPELINE_GOVERNANCE_AND_STATE.md` §13. Spec: `docs/REQUIREMENTS.yaml` REQ-169 / REQ-170.
>
> **Do not edit the body below.** Corrections belong in the findings report or the design notes; the
> value of this file is that it is what was actually said, when it was said.

---

From the NCES CCD, we have a list of districts. What we want in the lct_db is daily instructional minutes for the elementary, middle, and high school bands for each of those districts. We have been building the acquisition pipeline — described in ACQUISITION_PIPELINE.md, PIPELINE_GOVERNANCE_AND_STATE.md, and the stage design notes in docs/technical-notes/acquisition-pipeline-stage-design-notes — in order to define the journey each district takes where we acquire bell schedule information from URLs, process it into multiple representations, extract the bell schedule information by band, transform that banded bell schedule information into banded daily instructional minutes information, and then integrate that extracted information into lct_db.

Initially as a human factors design choice for the high supervision phase of the ramp-up model, we introduced batches (Stages 1-4) and dispatches (stages 6-7). By working in sets rather than one district at a time, we could be more efficient with human attention on supervision tasks and on clicks for approval tasks. We then started to look at a different challenge: in order to get from a high supervision state of operations to a high automation state of operations, we need to be able to test different CLI tools, APIs, search queries, AI model prompts, configurations, and settings. In order to do that, we know that we need to be able to test, measure, and train. Inspired by batch_000) — a set of "ground truth (GT)" districts where we had already manually collected bell schedule information (as a part of two previous attempts at bell schedule extraction pipelines) — we decided to formally add another layer to the already existing constructs of batches and dispatches: handling instructions for the pipeline.

What we are now formalizing, gap-filling, and building is an approach where both batches (stages 1-4) and dispatches (stages 6-7) have three different types that the pipeline handles in different ways:
- First run: the ideal case we are striving for is where we are able to efficiently and effectively collect bell schedule information (and, when we're lucky, direct declarations of daily instructional minutes) on each district's first run through the pipeline.
- Follow-up: functionally similar to first run, but more automated by default as authorization is granted by decisions at gate@5 or gate@7. The purpose of follow-ups to attempt to collect infromation that a first run wasn't able to surface.
- Benchmark: these are pipeline runs where the represenations of disovered URLs or the distract-band facts extracted from representations are strictly for testing and training the pipeline and running experiments. While the exact same representations and/or facts might come through a first run or follow-up batch or dispatch, information from benchmark batches or benchmark dispatches simply isn't on a pathway to get integrated into lct_db. We want clean information-handling rules in order to limit the risk of database corruption.

Details worth noting:
- While a benchmark batch is effectively self-contained, a benchmark dispatch can draw from representations that emerged from any batch type: benchmark, follow-up, or first run. While the two constructs are coneptually related, they are functionally indeprenct .
- Districts can and will make multiple runs through the pipeline. The fact of district having been on a benchmark batch/dispatch does not preclude it from being in a first run or follow up batch/dispatch, and the fact of a district having been in a first run or follow-up batch/dispatch does not preclude it from being in a benchmark dispatch.