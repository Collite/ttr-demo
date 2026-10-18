# The psql seam of data/automation — data/extend's, sourced (one place knows psql: CTX=<kube-context> |
# docker:<container> | local). Callers set CTX, POD, NS before sourcing.
# shellcheck source=../extend/lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../extend/lib.sh"
