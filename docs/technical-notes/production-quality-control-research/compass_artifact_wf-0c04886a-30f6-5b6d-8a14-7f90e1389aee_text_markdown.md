# Proving It's Safe to Relax a Human-Review Gate to Auto-Accept: A Technical Decision Framework

## TL;DR
- **You can justify relaxing a gate only by combining four things**: (1) a *calibrated, distribution-free error certificate* that bounds the mistake rate inside the auto-accept region at a chosen confidence (via selective-classification / conformal-risk-control methods, not raw softmax scores); (2) *subgroup-stratified validation* on a held-out set that mirrors production plus adversarial edge cases; (3) *shadow/canary deployment with continuous audit* and drift-triggered automatic re-escalation governed by an error budget; and (4) a *structured safety case* (GSN/assurance-case style) documenting the argument, evidence, and the conditions under which the argument stops holding.
- **Confidence-based thresholds alone are contested.** A threshold θ on a calibrated score can be given finite-sample guarantees (Geifman–El-Yaniv SGR; Learn-Then-Test; conformal risk control), but the learning-to-defer literature (Madras–Pitassi–Zemel; Mozannar–Sontag) shows a threshold that ignores the human's own error profile and cost structure is generally suboptimal — and even a "risk-controlled" empirical threshold carries *no* guarantee unless it is certified with a proper multiple-testing correction.
- **"Safe" is not static.** Real deployments demonstrate over-automation produces documented false-positive spikes — YouTube removed 11.4 million videos in Q2 2020 (roughly double the prior quarter's 6.1 million) after leaning on automation during COVID, with appeals rising from 166,000 to ~325,000; the gate must be monitored with sequential/SPC methods (CUSUM, burn-rate alerts) and drift detectors (PSI/KL), with a pre-committed rollback policy that re-escalates to human review when the calibration certificate is violated.

## Key Findings

1. **Calibration is necessary but not sufficient.** A score is calibrated if, among items scored p, a fraction p are actually correct. Modern neural networks are systematically overconfident (Guo et al., 2017), fixable post-hoc with temperature scaling, but calibration measured on a validation set does *not* survive distribution shift and is weakest in the high-confidence tail — exactly the region you auto-accept from. Calibration should therefore be treated as an input to threshold-setting, not as the safety guarantee itself.

2. **The safety guarantee comes from selective-risk control, not from calibration metrics.** Selective classification (Chow's reject option → El-Yaniv & Wiener → Geifman & El-Yaniv) formalizes "auto-accept when confidence > θ" as a risk-coverage tradeoff, and gives high-probability finite-sample bounds on the selective risk (error rate among accepted items). Distribution-free methods — RCPS, Learn-Then-Test, conformal risk control — turn "pick θ so error ≤ α" into a statistically valid certificate at confidence 1−δ.

3. **Learned deferral can beat confidence thresholds when the human is imperfect.** Learning-to-defer (L2D) jointly optimizes the model and the defer policy accounting for the human's accuracy/bias and the cost of deferral. This matters when the "human review" you are removing is itself noisy or biased.

4. **Monitoring must be sequential and pre-committed.** Once relaxed, the gate needs shadow-mode validation, ongoing stratified + near-threshold audits, sequential change detection (CUSUM/SPRT/Page-Hinkley), distributional drift detection (PSI/KL), and an SRE-style error budget with burn-rate alerts that automatically re-escalate the gate.

5. **Safety-case methodology from autonomy gives the documentation backbone.** GSN assurance cases, SOTIF/ODD framing, UL 4600, and the AMLAS framework provide a mature template for arguing "it is acceptable to remove the human here," including the requirement to state the operating domain, residual risk, and monitoring plan explicitly.

## Details

### 1. Confidence calibration

**Definition.** A probabilistic classifier is *calibrated* if its confidence matches empirical accuracy: of all predictions made with confidence p, a proportion p are correct. This is the property that makes "confidence > θ ⇒ safe to auto-accept" meaningful.

**Measurement.**
- **Reliability diagrams** (DeGroot & Fienberg, 1983; Niculescu-Mizil & Caruana, 2005) plot accuracy vs. confidence in bins; the identity line is perfect calibration.
- **Expected Calibration Error (ECE)** (Naeini et al., 2015) is the bin-weighted average gap between confidence and accuracy; **Maximum Calibration Error (MCE)** takes the worst bin — more relevant for safety-critical gates.
- **Brier score** (Brier, 1950) and **negative log-likelihood** are proper scoring rules combining calibration and sharpness.
- Binning-based ECE is sensitive to bin width; cumulative/ECCE variants (Arrieta-Ibarra et al., 2022) avoid binning artifacts. Kumar et al. (2019) showed common recalibrators are less calibrated than reported and introduced a scaling-binning calibrator with sample-complexity analysis.

**Recalibration methods.**
- **Platt scaling** (logistic fit on scores), **isotonic regression** (non-parametric monotone fit), **histogram binning**, and **temperature scaling** (Guo et al., 2017) — dividing logits by a single scalar T learned by NLL on a validation set. Temperature scaling is the standard because it is one-parameter, preserves accuracy/argmax, and works well.
- **Conformal prediction / conformal risk control** (Vovk; Angelopoulos & Bates) provides distribution-free, finite-sample coverage guarantees under exchangeability and is complementary to point calibration.

**Pitfalls.**
- **Overconfidence of deep nets** (Guo et al., 2017): increased capacity and reduced regularization degrade calibration even as accuracy rises. (Minderer et al., 2021 note some modern architectures — ViT, MLP-Mixer — are better calibrated, so this is architecture-dependent, not universal.)
- **Calibration drift / distribution shift**: calibration and accuracy both decay under shift (Ovadia et al., 2019); a calibration set that does not mirror production traffic gives a false certificate.
- **Tails vs. bulk**: aggregate ECE is dominated by the bulk of the confidence distribution; the auto-accept region lives in the extreme high-confidence tail where bins are sparse and calibration is least reliable. Measure calibration *conditional on the accept region*, not globally.

### 2. Selective prediction / learning-to-defer / abstention

**Selective classification (reject option).** The foundational error-reject tradeoff is Chow (1957, 1970). El-Yaniv & Wiener (2010) built the learning-theoretic foundations of noise-free selective classification and defined the **risk-coverage tradeoff**: a selective classifier (f, g) predicts with f when a selection function g accepts, else abstains; **selective risk** is the error rate on the accepted (covered) region, and **coverage** is the accepted fraction. Higher coverage generally means higher selective risk — this curve is the core object for gate relaxation. Your auto-accept region is exactly the "covered" region; escalation to a human is the "reject."

**Deep selective classification.** Geifman & El-Yaniv (2017) extended this to DNNs using softmax response or MC-dropout as the confidence score, and — crucially for gate-setting — gave the **SGR (Selection with Guaranteed Risk)** algorithm: given a target risk r*, confidence δ, and a validation set, binary-search a confidence threshold and return a high-probability bound b* on the selective risk (uniform-convergence guarantee). SelectiveNet (Geifman & El-Yaniv, 2019) trains prediction + rejection end-to-end for a better risk-coverage frontier.

**Learning-to-defer (L2D).**
- **Madras, Pitassi & Zemel (2018), "Predict Responsibly"** generalized rejection learning to *deferral*: the model can PASS to a downstream decision-maker, and training accounts for that decision-maker's accuracy and biases — optimizing the *whole system*, not the model in isolation. This is the key conceptual move: the value of auto-accepting vs. escalating depends on how good the human reviewer actually is.
- **Mozannar & Sontag (2020)** gave the first *consistent* surrogate loss for multiclass L2D via a reduction to cost-sensitive learning with an augmented label space (classes ∪ {defer}), generalizing cross-entropy. Follow-ups (Verma & Nalisnick 2022, one-vs-all; Mozannar et al. 2023, exact algorithms; Cao et al.) refine consistency and calibration.

**Confidence-based vs. learned deferral — the central debate.** Confidence-based deferral (threshold on a calibrated score) is simple, auditable, and can be given distribution-free guarantees, but it is provably suboptimal when the human's error profile is non-uniform or correlated with model errors: it defers where the *model* is unsure, not where *the human adds the most value*. Learned deferral targets system-level cost but requires human-decision data, is harder to certify, and can propagate miscalibration (Mozannar & Sontag's softmax surrogate was shown to mis-calibrate the estimated expert-correctness probability, motivating OvA variants). For a gate-relaxation decision, confidence-based thresholds with conformal certificates are the defensible default; learned deferral is warranted when the human reviewer is demonstrably imperfect/biased and you have logged human decisions.

### 3. Methodology for setting and certifying the threshold θ

The goal: choose θ so that **P(error | auto-accepted) ≤ α** holds with statistical confidence, and prove it.

**Risk-coverage curve first.** Sweep θ on a held-out set, plot selective risk vs. coverage. This shows the achievable operating points and the coverage you sacrifice to hit target risk α.

**Distribution-free finite-sample certificates.**
- **SGR** (Geifman & El-Yaniv, 2017): high-probability selective-risk bound at chosen δ; on ImageNet top-5 it guaranteed 2% error at ~53% coverage with δ=0.001.
- **RCPS — Risk-Controlling Prediction Sets** (Bates, Angelopoulos, Lei, Malik & Jordan, JACM 2021): choose a threshold parameter so expected loss is ≤ α with probability 1−δ, using concentration inequalities (Hoeffding, empirical-Bernstein, Waudby-Smith–Ramdas betting).
- **Learn-Then-Test** (Angelopoulos, Bates, Candès, Jordan & Lei, arXiv 2021; *Annals of Applied Statistics* 19(2):1641–1662, 2025): frames threshold selection as *multiple hypothesis testing* — each candidate θ is a null hypothesis "risk > α," and family-wise-error-controlling procedures (e.g., fixed-sequence testing) yield a set of θ with valid risk control even for non-monotone risks. This is the rigorous way to pick θ from a grid.
- **Conformal risk control** (Angelopoulos, Bates, Fisch, Lei & Schuster, ICLR 2024) extends conformal prediction to control the expectation of any monotone bounded loss.
- **Caveat from the literature**: tuning θ so empirical calibration-set risk is below α and declaring victory ("the Naive rule") carries *no certificate* — its failures "break no theorem" and create a false sense of safety (arXiv 2606.15153). The certificate requires the multiple-testing correction, and adaptive/post-selection threshold choice from a grid requires joint finite-sample treatment (e.g., adaptive selective conformal risk control).

**Sample-size / confidence bounds.** For a binary "error/no-error" outcome on audited accepted items, an exact **Clopper-Pearson** interval (Clopper & Pearson, 1934) gives conservative, finite-sample bounds on the true error rate (via Beta quantiles / inverted binomial CDF). It is conservative — Wilson score or Agresti-Coull are tighter and often preferred — but Clopper-Pearson is the standard when you must *guarantee* coverage. Practically: to certify a very low error rate you need many accepted-and-audited items, especially when zero errors are observed (rule-of-three: the 95% upper bound on a rate given 0/n events is ≈ 3/n).

**Stratification by subgroup/slice.** Aggregate risk control can mask a high-error subpopulation. The literature on selective classification under distribution shift and on hidden stratification requires validating risk *within* each meaningful slice (language, content type, customer segment, device, demographic proxy). A gate that is safe in aggregate but fails on a 5% slice is not safe. Set per-slice risk budgets and certify the worst slice, not the mean.

**Eval-set design.** The held-out/calibration set must mirror production (exchangeability is the assumption underlying all conformal guarantees); if production drifts, the certificate voids. Before relaxing, add **adversarial and edge-case stress testing** — the SOTIF distinction between known-unsafe and unknown-unsafe scenarios applies directly: actively search for triggering conditions that break calibration in the accept region.

### 4. Monitoring a relaxed gate and automatic re-escalation

**Shadow / canary first.** Run the auto-accept decision in *shadow mode* (log what would have been auto-accepted while humans still review everything), then **canary** to a small traffic fraction. This is the SRE canary pattern: roll out to 1% and you burn budget 100× slower, buying time to detect problems (Google SRE Workbook). Compare canary vs. stable before widening.

**Ongoing audit sampling.** Continue human review of a sample of auto-accepted items:
- **Stratified random audit** across slices to detect hidden high-error segments.
- **Targeted audit of near-threshold items** (just above θ), where risk is concentrated and calibration is thinnest.
- Audit rate is itself a debate: too low and you cannot detect a rate change quickly; too high and you defeat the automation's purpose. Tie the rate to the statistical power needed to detect a meaningful error-rate increase within your error-budget window.

**Sequential change detection.** Use methods designed for streams, not repeated fixed tests:
- **CUSUM** (Page, 1954; Hinkley, 1971) and its variant the **Page-Hinkley test** — accumulate deviations of the observed error/miscalibration metric from its in-control mean and alarm when the cumulative sum exceeds threshold h. CUSUM is a likelihood-ratio construction (related to **SPRT**, Wald) and detects small persistent shifts earlier than per-batch thresholds. Recent work applies CUSUM specifically to monitoring the *calibration* of probability forecasts for drift detection (arXiv 2510.25573).
- **EWMA** on the misclassification rate is a common alternative.

**Distributional drift detection (input-side, label-free).**
- **Population Stability Index (PSI)** — equal to the symmetric **Jeffreys divergence** (D_KL(P‖Q)+D_KL(Q‖P)); the credit-risk convention flags PSI > 0.1 as moderate and > 0.2 as significant drift.
- **KL divergence**, **Jensen-Shannon divergence**, **KS test**, **Wasserstein distance** on feature/score distributions. These are *leading* indicators (drift happened) that should trigger a targeted labeled evaluation (the confirmation), since covariate drift may or may not degrade accuracy.

**Error budgets / SLOs (SRE practice).** Define the gate's SLO (e.g., "≤ α false-accept rate over 30 days"); the **error budget** is (1−SLO)×volume. Use **multi-window, multi-burn-rate alerts** (Google SRE Workbook, Ch. 5): the recommended configuration pages when the 1-hour burn rate exceeds 14.4× *and* the 6-hour burn rate exceeds 6× the SLO error ratio — i.e., 2% budget consumption in one hour and 5% in six hours (a 14.4× burn exhausts a 30-day budget in ~50 hours), while a slower burn such as 10% budget consumption over three days opens a ticket rather than paging. Pre-commit an **error-budget policy**: when the budget is exhausted or a burn-rate/CUSUM/drift alert fires, the gate **automatically re-escalates to manual review** (the analog of an SRE deploy freeze / rollback). This converts "is it still safe?" from an opinion into a data-driven, automatic action.

### 5. Prior art and case studies

**(a) Human-in-the-loop ML.** The human-factors framing (Lee & See, 2004; Parasuraman & Riley's use/misuse/disuse) targets *appropriate reliance* — avoiding both over-reliance (misuse) and under-reliance (disuse). Empirical HCI work shows AI *confidence* signals shape reliance (Zhang, Liao & Bellamy, FAccT 2020) and that **miscalibrated confidence degrades human decisions and is hard for people to detect** (arXiv 2402.07632). This is directly relevant: while the gate is still human-reviewed, showing model confidence changes reviewer behavior, so audit reviewers should be blinded to model confidence to get unbiased error estimates. Active learning is the natural connection for the escalated stream — route near-threshold/uncertain items to humans and feed labels back to improve the model and recalibrate.

**(b) Content moderation (documented incidents of over-automation).**
- **Threshold-tiered routing is standard**: high-confidence → auto-remove/demote; low-confidence → human queue; mid-range → soft action (warning label). This is the exact "confidence-escalating auto" pattern.
- **YouTube, COVID-19 (2020)**: with human reviewers sent home, YouTube leaned on automation and *over-removed*. Per its Q2 2020 Community Guidelines Enforcement Report (reported by Axios and Tubefilter), it removed 11,401,696 videos — roughly double the prior quarter's 6.1 million — with 95% of videos removed at first detection found by software. Appeals rose from 166,000 to ~325,000 and videos reinstated after appeal roughly quadrupled from 41,000 to 161,000 — a documented miscalibration from over-automation. YouTube's mitigation was explicit tiering by confidence: it would "not issu[e] channel strikes on videos that were only flagged by its systems (without human review) — except in cases where the company had 'high confidence' that the content was violative."
- **Meta**: Meta's Oversight Board documented that during the Israel-Gaza conflict, Meta *temporarily lowered confidence thresholds* on its violent-content/hate-speech classifiers to remove content "even slightly likely to violate," which "led to drastic removal of non-violating content" (e.g., the Al-Shifa Hospital case), showing how lowering thresholds without human oversight harms public-interest speech. On January 7, 2025 Meta publicly reversed course ("More Speech and Fewer Mistakes"): it would "continue to focus these [automated] systems on tackling illegal and high-severity violations, like terrorism, child sexual exploitation, drugs, fraud and scams," while "for less severe policy violations, we're going to rely on someone reporting an issue before we take any action" and "require a much higher degree of confidence before a piece of content is taken down." Meta's transparency reporting quantifies the false-positive cost of automation: it reported cutting enforcement mistakes roughly in half from Q4 2024 to the end of Q1 2025, and reported enforcement precision of more than 90% on Facebook and more than 87% on Instagram in Q3 2025 — i.e., on the order of 1 in 10 removals still in error.
- **Lesson for gate relaxation**: platforms explicitly re-add human review tiers and raise thresholds after observing false-positive spikes — the empirical case for pre-committed re-escalation.

**(c) Autonomous-systems safety cases.**
- **Assurance cases / GSN** (Goal Structuring Notation, Tim Kelly, University of York): a safety case is a "structured argument, supported by a body of evidence, that provides a compelling, comprehensible and valid case that a system is safe for a given application in a given operating environment." GSN decomposes a top **goal** into sub-goals via **strategies**, bottoming out in **evidence (solutions)**, with explicit **context, assumptions, and justifications**. The Claims-Argument-Evidence (CAE) framework is the alternative notation.
- **SOTIF (ISO 21448)** addresses hazards from *functional insufficiencies* of the intended function (not faults) — precisely the ML case where a perception/decision model behaves as designed but fails on edge cases. Its scenario quadrant (known/unknown × safe/unsafe) drives you to shrink the "unknown-unsafe" region until residual risk is acceptable. The **Operational Design Domain (ODD)** defines the conditions under which the system is designed to operate safely — the direct analog of specifying the input distribution/slices within which your auto-accept gate is validated.
- **UL 4600** ("Standard for Safety for the Evaluation of Autonomous Products," Underwriters Laboratories / Edge Case Research, Koopman) is a claim-based safety-case standard for products operating "without human intervention." It explicitly addresses "changes required from traditional safety practices to accommodate autonomy, such as lack of a human operator to take fault mitigation actions," requires handling of "unknown unknowns," and mandates **Safety Performance Indicators (SPIs)** — leading and lagging metrics monitored in operation to validate that safety-case assumptions still hold. SPIs are the safety-case formalization of production monitoring + re-escalation.
- **AMLAS** (*Guidance on the Assurance of Machine Learning in Autonomous Systems*; Hawkins, Paterson, Picardi, Jia, Calinescu & Habli, Assuring Autonomy International Programme, University of York, 2021; arXiv:2102.01564) is the most direct bridge from ML to safety cases. It defines a **six-stage process** — (1) ML Safety Assurance Scoping, (2) ML Safety Requirements Assurance, (3) Data Management, (4) Model Learning, (5) Model Verification, (6) Model Deployment — each producing an instantiated **GSN safety-argument pattern**; the instantiated patterns together "constitute the safety case for the ML component." Its top claim is that the ML component "satisfies its allocated system safety requirements in the defined environment," decomposed into **performance** and **robustness** claims discharged by verification evidence. AMLAS explicitly requires considering "the contribution of the human as part of the broader system" — a human "may provide, for example, oversight or fallback in the case of failure of the ML component," and "any associated human factors issues, e.g. automation bias, should be reflected when allocating safety requirements to the ML component." It names the ML **"semantic gap"**: transferring perception/decision functions "from an accountable human agent to the machine learning component" opens a gap between implicit intentions and formalizable requirements "in an open context for which a credible, let alone complete, set of concrete safety requirements is very hard to formalise."
- **Waymo** frames the removal of the human as a formal safety case (Waymo, "A Blueprint for AV Safety," 2023; arXiv:2306.01917): "A safety case for fully autonomous operations is a formal way to explain how a company determines that an AV system is safe enough to be deployed on public roads without a human driver, and it includes evidence to support that determination," grounded in "absence of unreasonable risk." Notably, Waymo does not state a single quantitative threshold for removing the human — the determination rests on the full safety case plus a justification (its Case Credibility Assessment) that the acceptance criteria themselves are sufficient.

### Synthesis: a practical decision framework / checklist

**Phase 0 — Frame the gate (safety-case scoping, AMLAS Stage 1 / ODD).**
- State the *purpose* of the gate, the harm of a false auto-accept, and the cost of escalation.
- Define the **operating domain**: the input distribution and the enumerated slices within which relaxation is claimed. Anything outside is out-of-domain and stays escalated.
- Allocate a quantitative **risk target α** and confidence **1−δ** for the accept region, plus per-slice budgets.

**Phase 1 — Calibrate and characterize.**
- Recalibrate scores (temperature scaling default; isotonic if non-monotone distortion).
- Measure calibration *in the accept-region tail and per slice*, not just global ECE; plot reliability diagrams with error bars.

**Phase 2 — Set and certify θ.**
- Build the risk-coverage curve on a held-out set that mirrors production.
- Certify θ with a distribution-free finite-sample method: **SGR / RCPS / Learn-Then-Test / conformal risk control**, using a proper multiple-testing correction (never the "Naive" empirical-risk rule).
- Report the certified upper bound on selective risk (Clopper-Pearson or empirical-Bernstein on audited items) for the worst slice.
- If the human reviewer is known to be noisy/biased and you have logged decisions, evaluate a **learned-deferral** policy against the confidence threshold and adopt it only if it improves *certified system* risk.
- Run **adversarial / edge-case stress tests** (SOTIF unknown-unsafe hunting) before proceeding.

**Phase 3 — Deploy gradually (canary/shadow).**
- **Shadow mode**: log auto-accept decisions while humans still review; verify the production selective risk matches the certificate.
- **Canary**: enable auto-accept on a small fraction; compare canary vs. stable; widen only if the budget holds.

**Phase 4 — Monitor and pre-commit re-escalation.**
- Continuous **stratified + near-threshold audit** with reviewers blinded to model confidence.
- **Sequential detectors**: CUSUM/Page-Hinkley on audited error rate and on calibration; **drift detectors** (PSI/KL/JS/KS) on inputs and scores as leading indicators.
- **Error budget + multi-window burn-rate alerts**; a pre-committed **error-budget policy** that automatically re-escalates the gate to manual review when the budget burns, a detector alarms, or drift exceeds threshold.

**Phase 5 — Document the safety case (GSN / UL 4600 SPIs).**
- Top claim: "Auto-accepting items with score > θ in domain D keeps selective risk ≤ α with confidence 1−δ."
- Sub-claims: calibration adequacy; certified threshold; per-slice control; adversarial robustness; monitoring-and-rollback adequacy.
- Evidence: reliability diagrams, risk-coverage curves, certificate, stress-test results, canary results, monitoring design.
- **Explicit assumptions and their SPIs**: exchangeability/no-drift (monitored by PSI/KL), stable human-reviewer quality, stable input mix — each with a monitored indicator and a re-escalation trigger. State residual risk explicitly.

**What would change the decision (thresholds to re-tighten or re-escalate):**
- Audited selective risk upper bound exceeds α for any slice → re-escalate that slice.
- Burn rate exceeds the paging threshold, or CUSUM alarms on error/calibration → automatic rollback.
- PSI > 0.2 (or your calibrated threshold) on inputs/scores → recalibrate and re-certify before continuing.
- Change in the model, the upstream data pipeline, or the population served → certificate voids; re-run Phases 1–3.

## Recommendations
1. **Do not relax a gate on raw model confidence.** Require a distribution-free certificate (SGR / Learn-Then-Test / conformal risk control) on a production-mirroring, subgroup-stratified eval set, with the worst-slice risk — not the mean — meeting target α at confidence 1−δ. Reject any proposal that sets θ by simply checking empirical risk < α ("Naive" rule) — it has no guarantee.
2. **Stage the rollout**: shadow → canary → progressive widen, each gated on the production selective risk matching the certificate and the error budget holding. Use multi-window burn-rate alerts (page at 14.4× over 1h combined with 6× over 6h, per the Google SRE Workbook).
3. **Pre-commit the re-escalation policy before launch.** Wire CUSUM/Page-Hinkley (error + calibration), PSI/KL drift detectors, and error-budget exhaustion to an automatic fallback to human review. A relaxed gate without an automatic rollback path is not safe to relax.
4. **Keep auditing after launch**, stratified by slice and concentrated near θ, with reviewers blinded to model confidence to avoid automation-bias contamination of your error estimates. Size the audit rate to the power needed to detect a meaningful error-rate rise within one budget window.
5. **Consider learned deferral only when the human is imperfect** and logged human decisions exist; otherwise prefer confidence thresholds for auditability and certifiability.
6. **Write the safety case** in GSN/AMLAS/UL 4600 style, stating the ODD/domain, the certified claim, assumptions, residual risk, and the monitored SPIs that would falsify the argument. Treat gate relaxation like removing a human from a control loop — because that is what it is.

## Caveats
- **Open problem — confidence vs. learned deferral.** The field disagrees on whether calibrated confidence thresholds suffice or whether learned/joint deferral policies are needed; learned deferral optimizes system cost but is harder to certify and can itself be miscalibrated.
- **Certificates rest on exchangeability.** All conformal/selective-risk guarantees assume the calibration data and production data are exchangeable. Under distribution shift the guarantee silently voids — hence the emphasis on drift monitoring; robust/covariate-shift conformal methods exist but weaken the guarantee.
- **Audit-rate optimum is unsettled.** There is no consensus optimal ongoing-audit sampling rate; it trades detection power against the efficiency gains of automation and should be derived from your budget/power requirements, not a rule of thumb.
- **Calibration is not universal or permanent.** Whether modern nets are "badly calibrated" is architecture-dependent (Guo et al. vs. Minderer et al.), and calibration drifts; re-measure in the accept-region tail, per slice, on a cadence.
- **Some cited items are secondary or industry sources.** Company practices (Meta's January 2025 changes and precision figures, YouTube's 2020 data) are drawn from official transparency reporting/announcements, the Meta Oversight Board, and reputable press (Axios, Tubefilter); exact internal thresholds are not public. SRE burn-rate numbers come from the Google SRE Workbook. Several arXiv preprints cited for framing (e.g., the "false sense of safety" audit) are recent and not all peer-reviewed.
- **Statistical bounds require volume.** Certifying very low error rates (especially with zero observed errors) needs large audited samples; Clopper-Pearson is conservative, so low-traffic gates may be impossible to certify to a stringent α without accumulating data over a long window.