"""``python -m co_pymol …`` entry point — the same CLI as the ``co-pymol`` script.

Lets a generated MCP client config launch the package under a specific
interpreter (``<python> -m co_pymol proxy``) without depending on the ``co-pymol``
console script being on PATH. Routes straight to ``cli.main`` so there is one
argument parser and one ``proxy`` entry point.
"""

import sys

from co_pymol.cli import main

if __name__ == "__main__":
    sys.exit(main())
