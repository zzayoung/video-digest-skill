# 首页与新手体验 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement the documentation tasks below. This is a reversible documentation and sample-data change; verify working examples rather than adding implementation-mirroring tests.

**Goal:** Improve the GitHub homepage's clarity, first-success experience, and discoverability.

**Architecture:** Reuse the current renderer. Add a complete synthetic demonstration and make its download the first entry point. Keep detailed setup and platform requirements in INSTALL.md.

**Tech Stack:** Markdown, JSON, existing Python standard-library renderer, SVG, static HTML.

**Spec:** docs/superpowers/specs/2026-11-02-homepage-design.md

## Global Constraints

- Brand display: 片悟 · Pianwu; tagline: 学懂内容，拆出拍法。
- Repository URL and skill identifier remain the current technical identifiers.
- Do not change application behavior or install heavy models for documentation verification.
- Mark synthetic sample content; distinguish local preprocessing from the host Agent's model processing.
- Document transcript-dependent fourth output and adjacent asset dependencies accurately.

## Review Focus

- A beginner without Python can download and open the complete sample directory.
- A Python user can rebuild the sample without third-party packages or a model.
- A CLI-only user understands that all stops before Agent-authored outline content.
- Windows and macOS users see appropriate paths and commands.
- A user sharing generated pages understands which files must accompany the HTML.

## Tasks

- [x] Create examples/starter/outline.json and transcript.json; render docs/demo/; package docs/pianwu-demo.zip.
- [x] Rewrite README.md, README.en.md and INSTALL.md; update llms.txt.
- [x] Add a concise brand cover and reuse the existing actual renderer screenshot with an accurate caption.
- [x] Save sourced competitive-positioning and naming research in docs/positioning.md.
- [x] Run standard-library demo build, existing parser checks and link/asset checks. Browser interaction inspection is unavailable as recorded below.
- [x] Request an independent factual/onboarding review and fix the two substantive findings.
- [ ] Publish the reviewed change through GitHub.

## Verification boundary

The local browser runtime could not be installed from its download host. The available cloud browser does not share localhost and explicitly rejects file URLs. No workaround was attempted after that policy rejection. New screenshot capture and live interaction/mobile layout checks are unavailable in this run. Reuse the existing upstream screenshot, label it accurately, and verify the unchanged renderer through stdlib builds, links/anchors and existing tests.

Validation so far: Python 3.12 standard-library build creates all four demo outputs; regeneration matches byte-for-byte; 38 existing offline parser checks pass; 68 Markdown/HTML local references, SVG XML and ZIP contents verified. No product Python code changed.

## Independent review follow-up

Two important onboarding findings were accepted: WorkBuddy needed a ready-made import package, and loaded SKILL.md still contradicted the new docs on paths, image posts, mode behavior and the conditional transcript output. Correct those reference statements, provide a ZIP rooted at SKILL.md, and verify archive integrity. No runtime Python behavior changes. Cover labels use English to avoid missing CJK glyphs in font-limited renderers; Chinese branding remains real text in the README.

Both important review findings are fixed. A fresh extraction of the 44-file skill ZIP successfully rendered the four byte-identical demo outputs with Python -B -S; every archive entry matches its source. Old contradictory SKILL statements were removed, and the conditional transcript and host-model boundary are present. Demo inline JavaScript passes syntax parsing. All browser/host/live-platform limits remain explicitly unverified.
