"""Hardware access.

Real hardware classes import their GPIO libraries lazily, so this package can
be imported on a development machine. ``dte.sim`` provides drop-in simulated
versions of everything here.
"""
