# U05 cache-key observation

This is a prepared Academy fixture, not output from `$ca-debug` or `$ca-spike`.

## Observed behavior

An operator reported that reopening the local Workshop Queue report after switching
between two fictional tenant fixtures appeared to reuse the prior cache key.

## Reproduction

Inspect the report command, JSON-store boundary, and fixture paths before changing
anything. The report is local-only; there is no deployed cache, service account, or
production data involved.

## Expected behavior

The investigation must decide from cited repository evidence whether this is a real
defect, a design question, or an expected local-fixture observation. This U05 path is
prepared to take the real `$ca-debug` no-action exit: record the cited explanation in
the task board and make no product-code change.

## Spike question

If the no-action explanation still leaves a bounded implementation question, explore
only `U05 cache key` on the disposable spike branch. Transfer only the committed
findings file back to the parent; never merge or copy exploratory code.
