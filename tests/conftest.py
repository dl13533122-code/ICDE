"""Identify integration tests whose original processed datasets are not distributed."""
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA_REQUIREMENTS = {
    'test_fixed_roster_includes_sensor_quality_and_calendar_absence': [
        'data/processed/intel_daily.json'],
    'test_legacy_scalar_dataset_entrypoint_cannot_restore_intel_membership_strata': [
        'data/processed/electricity_verification.json',
        'data/processed/electricity_kwh_clipped.f32'],
}


def pytest_addoption(parser):
    parser.addoption('--require-data', action='store_true', default=False,
                     help='Fail collection if a selected data integration test lacks its original inputs.')


def pytest_collection_modifyitems(config, items):
    for item in items:
        required = DATA_REQUIREMENTS.get(item.originalname or item.name, [])
        missing = [p for p in required if not (ROOT / p).is_file()]
        if missing:
            reason = 'Original processed data not bundled: ' + ', '.join(missing)
            if config.getoption('--require-data'):
                raise pytest.UsageError(reason)
            item.add_marker(pytest.mark.skip(reason=reason))
