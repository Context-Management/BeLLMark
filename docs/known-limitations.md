# Known Limitations (v1)

- **LLM-as-judge is not ground truth.** Judge models have their own biases (self-preference, verbosity preference, position bias). Multi-judge evaluation mitigates but does not eliminate this.
- **Reproducibility is procedural, not bitwise.** LLM generation is inherently stochastic. Reruns produce comparable, not identical, results.
- **No built-in authentication.** Secure access using your infrastructure (VPN, reverse proxy, firewall).
- **Cloud API deployments transmit data to providers.** Only the local-only (LM Studio) configuration keeps all data on your infrastructure.
- **Judge prompts do not currently include anti-injection instructions.** Evaluated LLM responses could theoretically contain prompt injection attempts. Use trusted prompt suites.
- **Small sample sizes produce wide confidence intervals.** We recommend 15+ questions minimum; 26+ for reliable medium-effect detection.
- **PDF export may corrupt non-Latin-1 characters.** Use HTML or JSON exports for content with Unicode characters until the PDF engine is upgraded.
