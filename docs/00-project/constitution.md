# Project Constitution

- Version: 1.1.0
- Status: Accepted
- Authority: Highest product and engineering policy
- Date: 2026-08-03

## 1. Truth before convenience

Never fake print quality, repair success, color correctness, effective resolution, validation or PDF/X compliance. A convenient result must not replace measurable evidence.

## 2. Designer intent is protected

The original artwork is immutable. Every repair creates a derivative. AI may generate only an explicitly approved repair region such as bleed; it must not regenerate the original Trim Area.

## 3. Evidence before verdict

Every issue must reference a page, object, measurement or structural observation. Parser observations remain separate from rule conclusions.

## 4. Rules and deterministic algorithms before AI

Production priority is:

1. Versioned deterministic rules.
2. Traditional deterministic algorithms.
3. AI models behind an explicit safety gate.

LLMs explain and orchestrate decisions; they never edit PDF bytes or override a failed rule.

## 5. No fake resolution

Effective PPI is computed from source pixels and placed print size. Metadata changes and resampling do not erase the original measurement. Super-resolution is disclosed as enhancement, not restoration of known truth.

## 6. No silent font replacement

Exact font embedding requires identity and permission checks. Similar fonts require preview and explicit confirmation; otherwise the issue remains unresolved. Missing character mapping is a manual repair.

## 7. Print condition is versioned configuration

Every diagnosis and fix binds a Print Preset containing product, PPI, bleed, color policy, ICC identity and PDF/X target. There is no universal production CMYK default.

## 8. Automation is risk-tiered

Every repair declares exactly one safety class:

- `auto`: deterministic, reversible derivative with high-confidence evidence.
- `confirm`: preview and explicit user approval required.
- `manual`: the system cannot safely create or infer the missing production information.

Confidence, method and remaining limitations are visible.

## 9. Validation after every mutation

The required workflow is Analyze → Plan → Repair → Analyze Again → Validate → Export. Internal preflight, independent standards validation and printer acceptance are distinct results.

## 10. PDF/X claims match evidence

Metadata, OutputIntent and successful syntax checks produce a PDF/X candidate only. The `validated` state requires an approved independent PDF/X validator for the target profile.

## 11. Temporary processing and privacy by default

Upload is not permanent storage. Source files, extracted assets, previews and production PDFs expire automatically and may be deleted immediately by the user. Long-lived data is limited to necessary technical metadata, decisions and outcomes that cannot reconstruct the design.

Using artwork or image regions for model training requires a separate explicit opt-in.

## 12. Every production decision is versioned

Rules, Rule Sets, Print Presets, engines, models, ICC profiles and fix plans have stable identities and versions. Every derivative records source/output hashes and provenance.

## 13. Licensing is an architecture and release gate

AGPL/commercial license decisions are resolved before closed-source Alpha deployment. Process or service boundaries must not be presented as legal conclusions.

## 14. Specifications and tests evolve with code

Product promises require PRD updates. Architecture boundary changes require ADRs. New input formats require RFCs. New rules require positive, negative and boundary fixtures in the same change.

## 15. Humans remain final production authority

The product automates knowledge and repetitive operations. Designers and print providers retain authority over creative intent, target print conditions, high-risk repairs and final production acceptance.

Any implementation that violates this Constitution must change, regardless of implementation cost or apparent AI capability.
