"""Registered entry for the isolated channel suite, no production grant."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'migration-prep'))
from korea.test_phase_c_channel import ChannelTests
