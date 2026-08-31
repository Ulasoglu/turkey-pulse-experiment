from pathlib import Path

import filter_signals

# The production workflow runs prepare_municipal_registry.py first. At that point
# municipal_sources.json already contains every historical/current override.
# Prevent filter_signals.py from re-applying only the legacy override file and
# accidentally reverting newer validation rounds back to paused states.
filter_signals.MUNICIPAL_OVERRIDES = Path("__effective_registry_already_prepared__.json")
filter_signals.main()
