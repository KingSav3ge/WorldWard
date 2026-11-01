# Proposed Creator host characterization cases

Status: **review cases, not executable tests or passed evidence**. Engine review
branch based on `ecca8094a2d2cdb8a11e018a085487288b26e88d`. These cases
characterize the proposed [host contract](DRAFT_HOST_ATOMIC_CONTRACT.md) for
the App owner and coordinator to turn into real authenticated host tests.
Do not enable durable Creator creation until the contract is agreed and these
cases pass on the actual selected host. Use synthetic stores, private markers
and explicitly selected drafts; never open user saves or make provider calls.

## Known source characterization, not a Creator result

At App `c04ba5524ae95316c7e826fc63085a4916d7dd67`,
`IRGS_Web/server.py::Store.write` flushes and fsyncs a temporary file, replaces
the campaign path, then calls `sync_parent`. A parent-sync exception can follow
visibility of the complete replacement. `Store.action_result` retries the
directory sync for certain existing gameplay requests before returning a saved
result. `IRGS_Web/assistance.py::SoloService.rotate_restore` changes a private
guard in separate metadata before restore. The current Store uses a process-local
lock, not verified cross-process serialization. The App authenticates one local
owner with explicit Creator mode, not separate user accounts or memberships.
The save ID is public and also used as Engine branch ID; the private restore
guard and state digest are distinct. The existing
`test_intent_bridge.IntentBridgeTests.test_failed_save_restart_and_uncertain_sync_recover_original_once`
covers a gameplay request, not Creator creation or crash durability. App's
`sync_parent` is a no-op on Windows; do not infer Windows durability from POSIX.

## Cases to implement and execute at the actual host boundary

Each case uses the real authenticated Creator guard and normal draft initializer
for both selected profiles where applicable. Record exact Engine/App/Catalog
commits, commands, OS/filesystem and injected point. Observe both public
responses and trusted host state; raw state must never become browser output.

1. **Review and cancel:** Preview both bounded drafts. Capture campaign listing,
   save bytes and creation index before/after validation, cancellation and
   unaccepted creation. Assert no world, request receipt or new creation binding
   is published; preview identities cannot authorize a subsequent action.
2. **Pre-publication failure:** Fail temporary write, file flush, file fsync and
   replace separately. Where the host can prove replace never happened, expect
   definite rejection and no visible campaign, owner record or result. Reusing
   the same authorized request after recovery must follow the host's documented
   reservation/retention rules.
3. **Visible but unconfirmed:** Cause parent-directory sync to fail immediately
   after the successful atomic replacement. Assert that the complete envelope
   may be present but no success is acknowledged; status is
   `confirmation_pending`, with only the original request ID and no private
   scope or actor view. An exact authorized retry must not reinitialize or write
   another campaign. Make sync succeed; then obtain the stored original receipt
   exactly once. Assert actor-filtered view and unchanged physical effects.
4. **Repeated uncertainty and unauthorized callers:** Keep directory sync
   failing over status/retry and assert the result remains pending; altered
   bound payload conflicts without mutation. Deny an unauthenticated session,
   non-Creator mode and forged request/save/handle without disclosing whether
   the request exists. Do not invent separate App accounts for this test.
5. **Restart on each side of publication:** Interrupt before replace, after
   replace but before directory sync, and after confirmed sync before the
   response. Restart the real host. The last case returns the identical original
   receipt. In the middle case, test both surviving and lost directory entries.
   If a surviving envelope matches, revalidate and confirm it without
   reinitialization; if it vanished and no separately durable request evidence
   proves a safe disposition, fail closed rather than guessing rollback or
   silently creating again. Simulate loss with isolated filesystem fixtures;
   distinguish injected faults from real filesystem crash qualification.
6. **Concurrency and collision:** Send identical requests from separate host
   processes, then same request ID with changed draft or save and two distinct
   requests for the same save identity. Assert one coherent tuple, one
   initializer/effect at most, exact original result for identical retries, and
   safe conflicts. Test authorization using the real local-owner/session/Creator
   guards; do not forge unimplemented account identities. In-process threading
   alone does not establish multi-process serialization.
7. **Historical versus live scope:** The validated public save ID may be
   returned and is also the existing Engine branch ID; assert it is not treated
   as authorization. Put distinctive synthetic markers in private restore guard,
   state digest, unrelated actor and raw draft, then audit all nested public
   pending/confirmed fields for those markers. The optional history handle should
   initially be omitted; if later selected, it is random, separately stored and
   non-authorizing. An attempt to submit it as current authority fails.
8. **Restore and discarded future:** Create and play, preserve the original
   receipt, prepare a later action, restore earlier state with a fresh private
   guard, then attempt that action and old current-view guards. They must fail.
   An authorized original creation retry returns the same original historical
   receipt without recreating state or disclosing the new guard; fresh actor view
   and commands require current authentication and scope. Inject failures around
   both campaign and guard persistence; never expose a mixed restored state.
9. **Trash, deletion and evidence retention:** Exercise authorized trash,
   restore, retained tombstone and eventual retention expiry. A creation retry
   must not resurrect a trashed/deleted campaign or reveal protected data to
   an unauthorized session. Missing or inconsistent request/receipt/local-owner
   binding evidence is recovery-required until the host proves a safe
   disposition; no automatic replacement is allowed.
10. **Later play and full replay:** After confirmed creation, commit a supported
    action, reload/restart and replay the original creation request. Assert the
    original initial actor view, not the newer world view, and no second effects,
    stock transfer, elapsed work, initializer or provider request. Confirm the
    two drafts create independent worlds and preserve unknown historical time.

Negative tests must verify no newly granted stock, authority, consent or civil
hour; success means a supported exact result, not broader Alpha qualification.
The coordinator and App owner must explicitly settle DTO names, visibility,
transport/status codes, retention and crash-recovery implementation. This file
does not assert their agreement or implement any route.

## App-owner review and proposed primitive characterization

The App owner reviewed Engine `4053b5a2454b10cbe539b57ae265aaf6f34a5979`
and agreed with the proposed pending/rejection distinction and non-authorizing
history while identifying the local-owner and public save-ID boundaries reflected
above. Its immediate proposed slice is executable fault injection around the real
`Store.write`: verify old bytes survive a pre-replace failure, the complete new
record may be visible after parent-sync failure, and confirmation sync leaves the
campaign bytes unchanged. Those App tests are separately owned and have not been
run or incorporated here. Passing them would characterize the primitive only,
not establish Creator creation, atomic restore, cross-process safety or Windows
durability.
