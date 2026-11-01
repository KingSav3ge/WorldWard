# Bounded world-draft host creation and recovery contract

Status: proposed design contract for App/host review, amended 1 November 2026. The existing
Engine `world_draft` validates and initializes only the selected fictional Rise
and mixed historical-quay profiles. It creates an in-memory candidate; this
document does not implement durable creation, a host API, or a Creator playtest.
Preview remains disposable and its identities are not creation identities.

## Creation boundary

A trusted host authenticates and authorizes creation before accepting any draft,
request, or campaign identifier. The inspected App uses a single local-owner
session plus explicit Creator mode, not separate authenticated accounts or
persisted campaign memberships. A future implementation must bind its stable
request to that server-derived local-owner/store scope and recheck the existing
session, Host, Origin and Creator guards; it must not invent account principals
or take owner identity from the browser. The binding must survive authorized
session restart without treating a session token as the owner identity.

Bind the request to the exact draft, draft/review digests, explicit acceptance,
intended save and host-assigned scope. Bound and validate all fields. The current
App validates the public save ID before mapping it to a file; arbitrary request
IDs or browser-provided paths must not become filesystem paths or prove
authority. A changed bound field under the same request ID is a conflict, not a
second creation. Unauthorized callers and conflict responses receive no protected
campaign or request details. Support for multiple principals is outside this
local-owner proposal and must not be claimed without a separately designed host.

Under a serializable transaction or equivalent crash-safe compare-and-set, the
host checks request uniqueness and campaign absence, recomputes the Engine review
and invokes `world_draft.initialize` with the reviewed digests and explicit
acceptance. The candidate stays private until a single durable commit publishes
all of: initialized Core state, the server-derived local-owner/store binding,
campaign identity and associated private scope, an immutable request fingerprint
and the original actor-scoped public creation result. This binding describes a
future obligation, not an existing persisted membership feature. The result
identifies the public save and controlled actor, and contains only an
actor-filtered initial view plus an optional non-authoritative public history
handle defined below. It must not expose raw world, hidden template, other actor's
records, private draft contents, private restore guards or state digests.
A review digest is not an authentication token. Use only actual Engine data: do
not infer NPC consent, assets, resources or historical hours.

Before publication is attempted, a definite rejection (including stale review,
collision, lost authorization or initialization failure) must leave no visible
campaign, owner record, request receipt or partial save. Once an atomic replace
or equivalent publication may have occurred, a failure to confirm durability is
**not** a definite rejection. The complete tuple may already be visible; no
partial tuple may become authoritative. Concurrent identical requests must
produce at most one campaign and one result; conflicting requests cannot overwrite
one another. A success response is sent only after durability is confirmed.
Interruption requires the uncertainty recovery below. No provider dispatch
belongs in this transaction.

## Proposed result and durability states

These DTOs describe the proposed host boundary, not an implemented endpoint or
approved App representation. Authentication precedes any status lookup or
response; request IDs and handles never grant access.

- **definite_rejection**: the host knows that publication did not occur, or a
  conflict/authorization check rejected the attempt. Return a safe error with no
  creation receipt. A failed parent-directory sync after replace cannot be
  classified this way solely from the exception.
- **confirmation_pending**: publication may have occurred but durability is not
  established. An authorized caller receives
  `{"schema_version":"irgs-draft-create-status-1","status":"confirmation_pending","request_id":"<original>","retry":"same_request_only"}`.
  It contains no purported committed receipt or private scope. The host must not
  initialize again, allocate a replacement campaign, or invite a new request ID.
- **confirmed**: the host has established durability and returns the exact stored
  original `irgs-draft-create-result-1` receipt. Proposed fields are
  `schema_version`, `status: "confirmed"`, `request_id`, the existing
  public save `id`, `actor_id`, `initial_actor_view`, and optionally an
  opaque `creation_history_handle`. The save ID is not a secret or an
  authorization token; the current App uses this same value as `branch_id`.
  This proposal does not substitute that save ID for the Engine's distinct Core
  `campaign_id`, or require publishing the latter. App and Engine must agree on
  the final field names before implementation. The host authenticates and
  filters the actor view through existing Engine projections. A dedicated nested
  field audit must exclude private restore identifiers, state hashes, other
  actors' data and host internals; current Creator inspection projections are
  not evidence of an actor-filtered view. The first confirmed receipt and every
  authorized exact retry must be identical.

For a single-record host using a flushed and fsynced temporary file followed by
atomic replace and parent-directory sync, an error or interruption after replace
may leave a complete visible envelope without a confirmed directory sync. Under
the same writer lock or a serializable equivalent, recovery reauthenticates,
finds the same request and immutable bound fingerprint, verifies the complete
envelope and campaign/owner binding, and retries the required durability
operation. Only after confirmation may it return the stored original receipt.
A repeated sync error stays pending. A different payload, save identity or request conflicts safely. An unauthorized
session or non-Creator caller is denied without disclosing request or save data.
Retries must not call the initializer or repeat effects.

A restart after an unconfirmed publication can lose an unsynced directory entry.
Absence of the envelope alone does not prove no prior creation occurred. The host
needs a separately durable, recoverable request reservation/tombstone or an
equivalent proven protocol before it can distinguish safe rejection from unknown
history. If it cannot establish that distinction, fail closed with the same
request pending/recovery-required; do not silently recreate or assert rollback.
Retention, crash recovery and locking must work across concurrent processes, not
only within one worker. A successful directory sync is evidence for the supported
filesystem's contract, not a blanket claim about untested operating systems.

## Proposed public and private restore identities

The current App's validated public save ID is also its Engine `branch_id`; do
not classify that established identifier as secret or require a replacement.
The active private restore guard, guard derivation keys and world state digest
remain host-only. This proposal recommends initially omitting the optional
`creation_history_handle`. If later selected, the host may persist a separate
random opaque handle alongside the original immutable receipt, with no
derivation from private values and no authorization or submission authority.
It identifies only the historical creation event and is not a current scope. Following restore, the host generates a fresh private guard,
fences discarded-future requests and derives fresh current view/action guards
through the established host interfaces. Exact creation replay returns the
original historical receipt, never the new private guard or current view.
Authenticated current navigation uses a separate normal actor-view request.
A public campaign ID or historical handle is not evidence of current authority.
These rules still require App-owner reconciliation and security/recovery tests.

## Retry, continuation and restore

A retry is authorized under the same server-derived local-owner/store scope and
submits the same bound payload and request ID. It returns the exact stored public result, including its
original actor-scoped initial view, with no second initializer, effect, or write;
current world state must never be substituted for that result. An altered payload
is rejected even if the first response was lost. Subsequent game operations use
the existing shared-intent/communication APIs and their own scope and immutable
receipts; the creation receipt is not authority to submit them.

Backups/restores must preserve the local-owner/store binding, original creation
request fingerprint and receipt consistently with the campaign state. Restoring an earlier state
must install a fresh restore identity and fence submissions from discarded
futures. A pre-restore creation retry may return its original immutable receipt
only after authorization and only if the host can establish it belongs to the
same surviving creation; it must not re-create a deleted campaign or reopen a
discarded branch. The stored original restore identity is historical: it must not
be presented as the current submission scope. If identity or retained receipt
cannot be established, fail closed with a safe recovery status. A separate new
creation may be offered only after the host has conclusively resolved or retired
the old request under an explicit retention policy; never guess or silently
generate a replacement. Atomic restore must not
expose a mixed state/ownership/receipt set. Host retention and deletion policy
must specify how long retry evidence and tombstones survive, including backups.

## Inspected App boundary and unresolved implementation

At App `197d41a910b37b5c8b27d0f7dc9224b068244364`, `Store.write` replaces the
save before parent-directory sync; `Store.create` retains a request fingerprint
but replay returns current summary fields without reconfirming sync or preserving
an original initial actor receipt. Creator authorization is local-owner opt-in.
`ProcessService.scope` uses the public save ID as `branch_id`; restore guards
rotate in separate SQLite stores and optional Solo metadata before campaign
rename. The Store lock is process-local. No inspected behavior proves a durable
Creator request/tombstone protocol, cross-process serialization, atomic restore
envelope, nested projection safety or Windows durability.

The App owner agrees in review with rejection/pending/confirmed, same-request
recovery, immutable original receipts and non-authorizing history; this agreement
does not implement those properties. Its proposed immediate Store.write
fault-injection tests characterize the existing primitive only and are not
evidence of complete Creator recovery. This Engine branch does not enable
durable Creator creation. The public DTO and concrete implementation remain to
be reconciled and tested across both owners.

## Qualification required before claiming playtest support

Exercise both profiles through the real host and App: review and cancel without a
write; authorized explicit creation; exact retry after lost response, restart and
later play; concurrent identical and altered requests; identity collisions;
stale review; failed/partial disk writes and crash on both sides of commit;
unauthorized lookup; backup/restore and discarded-future fences; actor-filtered
results and actual subsequent play. Verify persistence on supported platforms and
run independent Catalog consumers using exact selected pins. No such host or App
qualification is claimed by this document.
