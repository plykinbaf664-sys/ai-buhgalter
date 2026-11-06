# Automatic historical source selection

Observed: equal FirstBit invoice timestamps stop basis resolution, and a supplier difference adds a separate archive-review button before the preview.

Change: keep live posted/client/contract/date filtering; use the existing `Date desc, Ref_Key desc` provider ordering as a stable tie break. Present a supplier difference inside the preview and use its existing versioned confirmation. Preserve source refs and read-back checks in the frozen basis.

Verify: tied history resolves reproducibly; a supplier difference reaches preview directly; changed supplier/amount invalidates the old confirmation; existing edit, write and recovery tests remain green. Production checks are GET-only until a user confirms a real preview.
