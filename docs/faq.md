# BeLLMark FAQ

Answers to the most common questions about installing, running, and licensing BeLLMark.

---

## General & Operations

### 1. Can I run BeLLMark on Docker?

Yes. Docker Compose packaging is included in the repository. See the `docker-compose.yml` file and the deployment guide in `docs/deployment.md` for setup instructions.

### 2. Which LLM providers are supported?

BeLLMark supports 11 providers:

1. OpenAI
2. Anthropic
3. Google (Gemini)
4. Mistral
5. DeepSeek
6. Grok (xAI)
7. GLM (Zhipu)
8. Kimi (Moonshot)
9. OpenRouter
10. LM Studio (local, OpenAI-compatible)
11. Ollama (local)

Local model support via LM Studio means you can run fully air-gapped benchmarks with no data leaving your machine.

### 3. What export formats are available?

BeLLMark supports five export formats:

- **HTML** — self-contained interactive report (light and dark themes)
- **PDF** — printable landscape report
- **PPTX** — slide deck for presentations
- **JSON** — structured data for programmatic use
- **CSV** — tabular data for spreadsheets

### 4. How many models can I compare at once?

Up to **6 models** in a single benchmark run. You can compare any combination of providers and models, including mixing local and cloud models in the same run.

### 5. Is there a minimum number of questions?

There is no hard minimum, but we recommend:

- **15+ questions** for meaningful statistical results
- **26+ questions** for reliable detection of medium-sized effects

Fewer questions reduce statistical power and widen confidence intervals, making it harder to distinguish real differences from noise.

### 6. Does BeLLMark send data anywhere?

It depends on which providers you use:

- **Local models (LM Studio / custom endpoints)**: No data leaves your machine. Fully air-gapped operation is possible.
- **Cloud APIs (OpenAI, Anthropic, Google, etc.)**: Prompts and responses are sent to those providers under their respective terms of service. BeLLMark itself has zero telemetry — no usage data is sent to BeLLMark servers.

### 7. Can I use my own evaluation criteria?

Yes. Evaluation criteria are fully customizable. You can define your own criteria, descriptions, and optional weightings. BeLLMark ships with sensible defaults, but nothing is locked in.

### 8. How does blind evaluation work?

BeLLMark uses dual-layer randomization to prevent bias:

1. **Blind labels**: Models are assigned blind labels (A, B, C, etc.) rather than their real names. The judge sees only labels.
2. **Presentation order shuffling**: The order of responses is independently shuffled for each judge evaluation.

The mapping between blind labels and real model names is revealed only after all judgments are complete. This eliminates both identity bias and position bias at the point of evaluation.

### 9. What statistics does BeLLMark compute?

BeLLMark computes a comprehensive set of statistical measures:

- **Wilson score confidence intervals** for win rates
- **Bootstrap confidence intervals** for score differences
- **Wilcoxon signed-rank test** for pairwise comparisons
- **Friedman test** for multi-model comparisons
- **Cohen's d** effect sizes
- **Holm-Bonferroni correction** for multiple comparisons
- **ELO ratings** with Bayesian adaptive K-factor
- **Length-controlled win rates** to separate quality from verbosity
- **Bias detection**: position bias, verbosity bias, self-preference bias

### 10. Can I export results for a client?

Yes. All benchmark results and exports are your property. You may share, publish, or deliver them to clients without restriction. See the licensing FAQ for details on output ownership.

---

## Licensing

### 11. How do we determine if our use is "commercial"?

Apply the conservative rule: **if BeLLMark is used by or for a for-profit entity, or used to support revenue-generating work, the use is commercial.**

This includes internal use at any for-profit company (regardless of whether BeLLMark is sold as a product), paid consulting work, and for-profit R&D. If you are unsure, email support@bellmark.ai.

### 12. I'm a freelance consultant. Do my clients need licenses?

No. One **€799 Commercial License** covers your use for all client engagements. Your clients receive outputs — they do not run BeLLMark themselves. Clients only need a license if they install and run BeLLMark on their own infrastructure.

### 13. Are the outputs (reports/exports) restricted?

No. Benchmark results and all exports are owned by the license buyer. You may share or deliver them freely.

### 14. Is there a license key or activation?

No. BeLLMark uses receipt-based licensing. There are no license keys, no activation servers, and no phone-home telemetry. Your receipt or invoice is your proof of license.

### 15. How do we purchase?

**Self-serve**: Card checkout is available at the product page.

**Invoice / Purchase Order**: Email support@bellmark.ai with your legal entity name, billing address, buyer contact, quantity, and PO number (if applicable).

---

## Additional Resources

- Full licensing details: [`docs/licensing-faq.md`](licensing-faq.md)
- Deployment guide: [`docs/deployment.md`](deployment.md)
- Known limitations: [`docs/known-limitations.md`](known-limitations.md)
- Refund policy: [`docs/refund-policy.md`](refund-policy.md)
- Support: support@bellmark.ai
