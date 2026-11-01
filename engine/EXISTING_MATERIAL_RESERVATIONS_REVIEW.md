# Existing R00 material reservation extraction — review candidate

Status: **unexecuted candidate, not a building-allowance implementation**.
Based on Engine `ecca8094a2d2cdb8a11e018a085487288b26e88d`; independent
Catalog revision 2 `ce4e503e7464e899092cb65917a1b005fa8a01c4` is an
unselected design reference, not a runtime dependency or adopted profile.

The current R00 model derives *unconsumed material* availability from active
projects in the actual household and separately protects seed grain. This
candidate extracts that calculation into a private Core helper used by the
existing `_free` path. It adds no state, second authority, public DTO,
building-place reservation, additional building identity, permission, duration,
or fictional profile. The active/paused/held rules, raw stock accounting and
seed protection are unchanged. Pausing releases unconsumed materials, not a
building place. The latter has no existing R00 representation.

`runtime/test_material_reservation_regression.py` proposes behavioral checks
against ordinary reviewed R00 creation: active founder and Oren work reserve
only their household's actual timber/tools, pause releases unconsumed material
without stock credit, resume re-reserves, completion consumes once, replay after
reload is effect-free, and R9 observes the project and stock dependencies. It
also checks delegated work and a separately initialized non-Rise quay action.
These tests have **not** been executed by the owner: no usable owner executor
is available. They are not evidence that full RISE-EXPANSION-01 works.

After independently checking the candidate and preserving any existing owner
work, the coordinator can run from the exact candidate Engine root:

```sh
PYTHONPATH=IRGS_3_3/runtime python -B -m unittest test_material_reservation_regression test_settlement test_ordinary_invitation_decision test_world_draft -v
python -B tools/verify_components.py --component engine
```

Also run the prescribed full safe-fixture runtime suite and any relevant App and
Catalog consumers before proposing adoption. Historical test results are not
fresh candidate evidence. No CI, browser, native Windows, live provider, 5.0
qualification or source parity is claimed.

Catalog v2 addresses the originally identified stock-credit ambiguity, seeds no
opening building, and permits both conflicting last-place requests to defer.
Remaining decisions include the council/steward relationship, an authority-safe
response when issuer or site review is missing, review expiry/renewal, old-save
compatibility, post-work disposition, and project/asset/place identity. Do not
equate the existing extraction with a selected allowance or expose another
household's hidden feasibility. The independently reviewed Creator contract is
on its own branch and is not modified here.
