# Boston Hydrant Map — Project Handoff

> Paste this entire file as the first message to Claude on your desktop.
> It contains everything needed to continue work without the VPS.

## What this is

A Progressive Web App that finds the nearest fire hydrants to any Boston
address. Built by a Boston FD firefighter as a workaround for NowForce dispatch
(which doesn't have hydrant data). Distributed via GitHub Pages + Google Play
Store (TWA wrapper). Independent reference — NOT officially affiliated with BFD.

- **Live PWA**: https://swolosaurus.github.io/bfd-hydrant-map/
- **GitHub repo**: https://github.com/swolosaurus/bfd-hydrant-map
- **User-site repo** (asset links only): https://github.com/swolosaurus/swolosaurus.github.io
- **Play Store**: Internal Testing only as of 2026-06-10

## Current state (as of 2026-06-10)

| Component | Version | Status |
|-----------|---------|--------|
| PWA | v69 | Live on GitHub Pages |
| TWA APK/AAB | v1.0.7 (versionCode 8) | Uploaded to Play Store Internal Testing |
| Cache (`sw.js`) | `bfd-hydrants-v69` | Live |
| Maps API budget killswitch | Deployed + tested ✅ | Cloud Run in `bfd-hydrant-map` project |
| Digital Asset Links | Both upload + Play App Signing keys | TWA fullscreen confirmed working |

## Key file locations (on this machine)

| Path | Purpose |
|------|---------|
| `C:\Users\Administrator\Desktop\Arcgis\hydrant-map\` | Main project repo |
| `C:\Users\Administrator\Desktop\Arcgis\swolosaurus.github.io\` | User-site repo (asset links only) |
| `C:\Users\Administrator\Desktop\Arcgis\hydrant-twa\` | Local bubblewrap workspace (keystore lives here) |
| `C:\Users\Administrator\Downloads\BFD UNIT LOCATIONS.doc` | Canonical BFD unit roster (2013 + D10 added) |

## Account map

| Service | Account | Notes |
|---------|---------|-------|
| Play Console | `bostonhydrantmap@gmail.com` | Paid $25. App owner. |
| Google Cloud (Maps API, billing, killswitch) | `alexander.cho.617@gmail.com` | Project owner. `bostonhydrantmap` also has Owner role (granted via IAM). |
| Chrome default | `eviltech@gmail.com` | No access to bfd-hydrant-map — use incognito or `?authuser=alexander.cho.617@gmail.com` URL trick. |
| AdSense | Not yet applied | When applying, use whichever Gmail doesn't already have AdSense (likely bostonhydrantmap). |

## Today's work (2026-06-10) — what landed

1. **PWA v69 + TWA v1.0.7**: renamed app from "BFD Hydrant Map" to **"Boston Hydrant Map"** (Play Store impersonation review risk mitigation). Subtitle changed from "BOSTON FIRE DEPARTMENT" → "BOSTON · INDEPENDENT REFERENCE".
2. **Play Console**: developer account paid + verified, app created (`io.github.swolosaurus.bfdhydrants`), AAB uploaded to Internal Testing track, installed on phone.
3. **Maps API safety net**: full end-to-end killswitch deployed and tested:
   - $1/mo budget with email alerts at 50/90/100%
   - Pub/Sub topic `budget-alerts` in `bfd-hydrant-map` project
   - Cloud Run service `disable-billing-on-alert` (us-central1) with `stopBilling` function
   - Service account granted `Billing Account Administrator` on the billing account
   - Synthetic "within budget" test returned `OK (within budget)` ✅
4. **IAM cross-account access**: `bostonhydrantmap@gmail.com` granted `Owner` on `bfd-hydrant-map` GCP project so cloud work doesn't need account-switching.
5. **Digital Asset Links fix**: TWA was showing URL bar after Play Store install because the asset links file only had the upload-key fingerprint. Added Play App Signing fingerprint too. KEY LESSON: the asset links file is served from the **separate user-site repo** at `swolosaurus.github.io`, NOT from the project repo. Must push updates to the user-site repo.
6. **CI workflow update**: GitHub Actions now signs the AAB explicitly via `jarsigner` after bubblewrap (bubblewrap only signs APK).

## Tomorrow's queue (priority order)

### 1. Beef up About page for AdSense scoring (medium effort, ~1-2 hr)
The About modal in `index.html` (search for `<div id="about-content">`) is too short for AdSense — they'll likely reject as "low value content". Need to add 800-1000 words of substantive content. Ideas:
- Hydrant color codes (NFPA 291): blue (1500+ GPM), green (1000-1499), orange (500-999), red (<500)
- Boston water system overview
- What "due" means (1st due, SS, 2nd, etc.)
- Why running cards exist
- Fire hydrant FAQs
- Glossary of BFD terms

### 2. Apply for AdSense
After (1) is done. Use `bostonhydrantmap@gmail.com` (assuming alexander.cho.617 doesn't already have AdSense — verify first). Site URL: `https://swolosaurus.github.io/bfd-hydrant-map/`. Expect 1-2 week review. First-time rejections common — keep iterating on content.

### 3. Play Console store listing (medium effort, ~2 hr)
Required before Closed Testing track can be created. Need:
- Short description (80 chars): `Find the nearest fire hydrants to any address in Boston, MA.`
- Full description (4000 chars): draft already saved in earlier chat. Includes "Not officially affiliated with the Boston Fire Department" disclaimer.
- App icon 512×512 — already have `icon-512.png`
- Feature graphic 1024×500 — NEED TO DESIGN
- 2-8 phone screenshots — NEED TO CAPTURE
- Category: Maps & Navigation
- Content rating questionnaire — fill in via Play Console
- Data Safety form — declares no PII collection (clipboard read only, no transmit)
- Privacy policy: `https://swolosaurus.github.io/bfd-hydrant-map/privacy.html` (already live)

### 4. Closed Testing 14-day track (the critical path)
Mandatory for new personal accounts before Production. Requires ≥20 testers for ≥14 days. Plan: invite crew, neighboring firehouses, family. Track starts when first build is rolled out + testers are added.

### 5. Box 9218 TL17 investigation (low priority, user research)
User said they'd "find out" what TL17 means on box 9218 (only remaining bogus token in non-9xxx running card after v68 cleanup). Once resolved, patch and ship.

### 6. 9xxx tunnel-zone running cards (deferred indefinitely)
50 boxes in tunnel/airport zones have multi-scenario structure that the current JSON schema can't represent cleanly. User confirmed the multi-scenario layout is INTENTIONAL on the actual cards (not OCR error). Picker filter (`UNIT_ALLOWLIST`) already hides any bogus tokens these contain from the UI, so functionally fine to leave alone.

### 7. Missing 4th engines on E59 group (deferred)
12 boxes in the E59 OCR cleanup pass had their 1st-alarm engine slot 4 visible on the card but missing from JSON. User said leave blank until they have time to dictate the fills. List: 3741, 3812, 3813, 3818, 3765, 3817, 3824, 3829, 3871, 3873, 3874, 3876.

## Critical context for new Claude sessions

### Cache version bumping
Every PWA code change requires bumping the cache version in BOTH:
- `sw.js` — `const CACHE = 'bfd-hydrants-vNN'`
- `index.html` — `const ver = 'vNN'` (search for that string near the bottom)

Then deploy via the `/pwa-deploy` agent (or commit + push manually). The agent handles verification.

### TWA version bumping
For TWA changes (renames, new icons, etc.), bump in BOTH:
- `twa/twa-manifest.json` — `appVersion`, `appVersionCode`, `appVersionName`
- `twa/app/build.gradle` — `versionCode`, `versionName`

versionCode must always increment. Pushing to `twa/**` triggers the GitHub Actions build automatically.

### Unit picker allowlist (UNIT_ALLOWLIST in index.html)
Strict roster from `BFD UNIT LOCATIONS.doc` (2013) + D10 added (D10 is real per current BFD ArcGIS, was missing from 2013 doc).
- Engines (33): E2-E10, E14, E16-E18, E20-E22, E24, E28-E30, E32, E33, E37, E39, E41, E42, E48-E53, E55, E56
- Ladders (22): L1, L2, L4, L6, L7, L9, L11, L14-L19, L21, L23-L26, L28, L29, TL3, TL10
- Specials (10): R1, R2, MU, MCP, MCT, W25, H2, H7, H8, HAZMT1
- Chiefs (12): D1, D3, D4, D6, D7, D8, D9, D10, D11, D12, Div1, Div2

### Asset links gotcha (the one that bit us today)
The `.well-known/assetlinks.json` file MUST be at the **root** of `swolosaurus.github.io`, served from the **separate user-site repo** at `https://github.com/swolosaurus/swolosaurus.github.io`. Updates pushed to the `bfd-hydrant-map` repo's `.well-known/assetlinks.json` will be served at `swolosaurus.github.io/bfd-hydrant-map/.well-known/...` which is NOT what Android validates.

### Both fingerprints required in asset links
- Upload key SHA-256: `E9:48:72:C3:5A:A2:5A:16:2F:9E:CD:ED:39:87:BD:03:A3:91:EF:12:7D:33:53:CD:FB:C9:90:70:9D:A5:2E:1F`
- Play App Signing SHA-256: `11:34:B0:98:F1:FD:88:C6:8E:F9:00:A3:D4:00:BD:4F:28:45:9E:B3:A6:2F:F4:A8:79:6C:D4:77:0C:15:25:80`

Both must be in `sha256_cert_fingerprints[]` array, or the TWA falls back to Chrome Custom Tabs with a visible URL bar.

### Don't suggest taking breaks
User preference: never suggest "come back later" or "take a break." Always offer concrete next-step options (deploy now, keep going, switch tasks).

## How to invoke Claude from desktop

1. Open Claude on desktop (claude.ai or Claude Code if installed).
2. Paste this entire file as the first message.
3. Add a one-line instruction at the bottom describing what you want to work on, e.g.:
   - "Let's start on tomorrow's queue item #1 — beef up the About page for AdSense."
   - "Help me write the Play Console store listing description."
   - "I want to capture screenshots for the Play Store listing — how?"

Claude won't have direct file access to the VPS, but can guide you through changes you make locally, and can review code/screenshots you paste. For file changes, work from your desktop clone of the repo or paste code snippets for review.

If you need to work directly on the VPS repo from your desktop later, clone the repos:
```
git clone https://github.com/swolosaurus/bfd-hydrant-map.git
git clone https://github.com/swolosaurus/swolosaurus.github.io.git
```

---

*This handoff written 2026-06-10. For anything not covered, see `project_hydrantmap.md` in the VPS memory directory — it has the full multi-month change log.*
