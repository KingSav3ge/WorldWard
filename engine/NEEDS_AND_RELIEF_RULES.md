# Ordinary needs, steward relief and the quay deadline

Adopted by the user on 24 November 2026 for gate A4-G04 (with bounded A4-G05
obligation and A4-G06 institution behaviour). These are authored, uncalibrated
fictional rules. They are not historical measurements or a universal needs model.
Existing Core, the nine K owners, the six Directors, actor-scoped information,
conserved stock and atomic rejection are unchanged.

Both rules are **opt-in reviewed setup choices**. Saves and fixtures created
without them behave exactly as before, and their review digests are unchanged.

## R00 profile `rise-needs-1`

Selected at Rise setup with `needs_profile: "rise-needs-1"`. The review shows
the rule text before the campaign is created.

### Hunger

- At each existing 6-hour provision boundary, the portions a household delivers
  go to its local members in membership order (founder first).
- A member who receives no portion becomes **hungry**. A member who receives a
  portion stops being hungry.
- A hungry person cannot start or resume settlement work. An active project
  whose worker is hungry is held at that boundary; completed work is kept.
- **Feed your household** (`feed_household`): at the household's stores, each
  hungry co-located member eats one free grain portion (never the protected
  seed), in membership order, while free grain lasts. At least one person must
  be fed. This rule assigns eating no elapsed time.
- No injury, illness or death is inferred.

### Fatigue

- Each person accumulates seconds of settlement work since their last rest,
  across projects.
- At **4 hours (14,400 seconds)** they are **tired**: their active project is
  held at that boundary and they cannot start or resume work.
- **Rest** (`rest`): the founder and any idle household members at the same
  place rest together. It takes **2 hours** where the household has a completed
  shelter at that place, otherwise **4 hours**. Time passes through the normal
  scheduler, so provision can occur during rest. Rest resets the count and
  clears fatigue for those who rested. Resting when not tired is allowed.

### Steward relief and its obligation

- Steward Elin holds a finite commons store of **8 grain portions**, a real
  conserved stock account (`steward-store`), not new stock.
- **Ask Elin for relief** (`request_relief`): at the commons with Elin. Elin
  decides by this authored rule:
  - She declines unless the household's most recent provision assessment
    recorded a shortfall.
  - She declines while any earlier relief obligation of that household is open.
  - She declines when her store is empty.
  - Otherwise she lends **2 portions per household member**, limited by her
    store. The founder carries them to the household stores.
- Each relief creates an obligation of **1 hour of footpath upkeep per 2
  portions** (rounded up), owed to the steward.
- **Work on the footpath** (`path_upkeep`): at the clearing, while relief is
  owed, the founder starts upkeep work of up to one hour. It needs no materials
  or tools. It is ordinary work, so hunger and fatigue apply. Completed upkeep
  reduces what is owed; the obligation is discharged when nothing remains.
- An open obligation changes later choices: Elin refuses further relief until
  it is discharged.

## Quay opening `quay-deadline-v1`

A fourth 1415 quay variant, *A dispatch against the hour*. The three existing
variants are unchanged.

- The clerk accepts the dispatch only if the hand-over **completes within 180
  authored seconds** of the opening. The review and map state this deadline.
- A hand-over that would complete later fails. It still takes its 10 seconds,
  and the courier keeps the dispatch.
- The closure persists: every later delivery attempt also fails.
- The fastest route (passage, desk, hand-over) takes 100 seconds. Looks, a
  failed gate attempt and backtracking can exhaust the time.
- No payment, punishment, office or historical consequence is inferred.

## Not covered

- Crops, trade, foraging, illness, injury, death, NPC rest, or needs for
  steward, Oren or Mira beyond the shared provision and hunger rule.
- Needs at quay timescales beyond the single deadline.
- Native Windows, live-provider and Alpha qualification remain open.
