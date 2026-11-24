# WorldWard 3.5.0 Pre-Alpha (branch build)

Joined on 24 November 2026 on branch `claude/laughing-brown-pkbs04` at the
user's direction. This is not a main publication; the component pull requests
were unmerged when the user approved these exact commits.

| Component | Commit | Source |
| --- | --- | --- |
| Engine | 4b94ec7755a950fc97e083d29f51b3772cb12fe1 | KingSav3ge/Fulcrum-Engine#3 |
| App | e1c82751520f1db1b9718b16803c285b96d5a3b4 | KingSav3ge/WORLDWARD-APP-WEB#7 |
| Catalog | 7ef54aba82d292f1a487e0253d8479abdc78dfda | unchanged from 3.4.9 |

## Changes

- Optional Rise needs profile `rise-needs-1`: hunger, fatigue, Steward Elin's
  finite grain relief and its footpath-upkeep obligation. See
  `engine/NEEDS_AND_RELIEF_RULES.md`.
- New 1415 quay opening `quay-deadline-v1`: a 180-second delivery deadline that
  closes delivery when missed. Existing quay openings are unchanged.
- Windows launcher looks for a working Python 3.12+ (`python`, `python3`,
  `py -3`) and explains how to install it. Not yet executed on Windows.

Saves and setups made without the new choices behave as in 3.4.9. All twelve
functional Alpha gates remain unqualified; native Windows and live-provider
checks remain outstanding.
