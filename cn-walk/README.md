# cn-walk — a throwaway branch (CN-P5 S5.4)

This branch exists for one end-to-end walk of the cn candidate store's promotion flow in Veles: candidates are
submitted, a steward promotes them, Veles opens a pull request against this branch, the pull request is merged here,
and the next model load marks the candidate promoted.

`model/` is ttr-core's golden Hartland world (`packages/kotlin/ttr-concept/src/test/resources/worlds/hartland/*.ttrm`
at `grammar/v0.18.3`), not the demo model. Nothing here is merged into `master`; the branch is deleted after the walk.
