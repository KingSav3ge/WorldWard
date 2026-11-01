# R00 continuing decision safety — review candidate

Status: **unexecuted Engine candidate**, based on published Engine
`ecca8094a2d2cdb8a11e018a085487288b26e88d`. The target is the existing
`rise-foundation-1` fictional R00 procedure, not a new NPC policy. The
selected initial setup controls only the founder. Oren's existing repair and
finite own-household provision determine the already implemented refusal or
agreement; departure and actual arrival are separate existing steps.

## Existing rule and bounded change

`settlement_runtime.py` says it makes no autonomous player-character
decisions. Before this candidate, `invite` and `arrange_departure` checked
location and existing grant/plan state but did not recheck whether Oren had
become player-controlled or was unavailable under an explicit temporal registry.
The candidate checks the existing Core player-actor list and the existing
`player_actions._present` rule at the actual decision/departure commit. An
ineligible attempt fails generically with no decision, new receipt, movement,
stock change or elapsed work. The actor's attempt menu does not inspect those
hidden conditions. Old states without a temporal registry retain the existing
presence fallback; no registry or new facts are installed.

Normal selected R00 outcomes, time model, existing source, exact wording and
Core ownership remain unchanged. Already committed requests replay their
original receipts before executing any new decision; no historical agreement is
rewritten. The change guards a new decision and new departure. It does not
define a new control-transfer policy, a right to interrupt an already departed
journey, a general NPC planner, additional consent, institutional authority,
risk procedure, need, or recovery model.

## Coordinator checks requested

At the exact review commit, use temporary synthetic stores and run:

```sh
PYTHONPATH=IRGS_3_3/runtime python -B -m unittest test_continuing_npc_control test_ordinary_invitation_decision test_draft_intent_offers test_settlement test_quay_contact_decision -v
python -B tools/verify_components.py --component engine
```

The new test module specifies normal reviewed Rise creation, actual early
refusal, existing repair, later agreement, separate departure, arrival, stock
conservation, save/reload, original-result replay and restore fencing. It also
uses explicitly labelled **synthetic** control and temporal-registry changes
to test no-effect rejection, actor-safe attemptability and preserved history;
these are not ordinary R00 controls. A separately initialized non-Rise quay
regression checks that its selected failed route, stock and historical time are
unchanged. Tests prohibit provider/network calls.

Run the prescribed safe-fixture full runtime suite and relevant App HTTP and
independent Catalog consumers against the exact eventual pins before adoption.
The candidate's source and test hashes were prepared in `release.json`, but no
component verification, Python test, HTTP, browser or native Windows run was
possible in the owner session. This note does not qualify any G04/G06/G07 or
5.0 gate. App/Catalog adoption, general needs/recovery, continuing institution
plans, contested shared-resource policies and an adopted consequential risk
profile remain open. Old owner-local work is inaccessible and must later be
reconciled; the material, Creator and launcher branches remain separate.
