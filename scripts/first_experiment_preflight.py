"""Offline inspection of F2.2 configuration; never authorizes or sends a call."""
import argparse
from datetime import datetime, timezone
from decimal import DecimalException
import json

from command_center.coding.first_experiment import CAP, FirstExperiment, task_payload
from command_center.coding.integration_config import IntegrationConfig
from command_center.store import Denied, digest


def inspect_config(config, now=None):
    now = now or datetime.now(timezone.utc)
    experiment = config.first_experiment or FirstExperiment()
    evidence = experiment.report(now)
    blockers = []
    if config.mode != 'live':
        blockers.append('live_mode_required')
    if not config.live_authorized:
        blockers.append('operator_live_flag_missing')
    if not config.first_experiment:
        blockers.append('first_experiment_profile_required')
    if not config.synthetic_repository:
        blockers.append('synthetic_repository_missing')
    references = [config.openai_secret_ref, config.github_secret_ref]
    paths = [config.credential_files.get(ref) for ref in references]
    if not all(references) or not all(paths):
        blockers.append('credential_references_missing')
    elif len(set(references)) != 2 or len(set(paths)) != 2:
        blockers.append('separate_provider_credentials_required')
    if not config.connected():
        blockers.append('connection_settings_incomplete')
    if not config.tariff or not config.tariff.confirmed or not config.daily_nano_rub or not config.monthly_nano_rub:
        blockers.append('budget_unconfirmed')
    maximum = config.tariff.maximum() * experiment.call_limit if config.tariff else None
    budget = maximum if maximum is not None else CAP
    if not 0 < budget <= config.monthly_nano_rub:
        blockers.append('invalid_task_budget')
    if maximum is not None and min(config.daily_nano_rub, config.monthly_nano_rub) < maximum:
        blockers.append('two_call_reservation_exceeds_configured_capacity')
    blockers.extend('evidence_missing_or_expired:' + key for key, current in evidence['gates'].items() if not current)
    try:
        # PURE validation only. True exercises the price/rounding checks after
        # the validator's consent guard. No Gateway/F1 action is instantiated,
        # and no approval is stored or inferred from this inspection.
        experiment.validate_scope(config, task_payload(experiment.id)['coding'],
            budget, now, final_confirmation=True)
    except Denied as error:
        blockers.append(str(error))  # Existing validator returns fixed codes only.
    return {'status': 'BLOCKED' if blockers else 'LOCAL_CHECKS_PASSED',
            'checked_at_utc': now.astimezone(timezone.utc).isoformat(),
            'experiment_id': experiment.id, 'model': experiment.model,
            'synthetic_base_sha': evidence['base_sha'], 'max_calls': experiment.call_limit,
            'max_budget_nano_rub': experiment.budget_cap, 'configured_two_call_reservation_nano_rub': maximum,
            'configured_reservation_nano_rub': maximum,
            'proposed_task_budget_nano_rub': maximum if maximum is not None and 0 < maximum <= CAP else None,
            'profile_hash': digest(config.model_dump()), 'blockers': sorted(set(blockers)),
            'live_call_allowed': False, 'final_owner_approval_verified': False,
            'remote_state_verified': False, 'provider_hard_cap_verified': False, 'credential_values_read': False,
            'external_calls': 0,
            'requires_separate_verification': ['account_model_access', 'app_and_repository_permissions',
                'credential_custody_and_revocation', 'runtime_and_database_ledger',
                'payment_terms_and_balance', 'dry_run', 'exact_final_owner_approval']}


def main():
    class SafeParser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(2, 'invalid preflight arguments; values not displayed\n')
    parser = SafeParser(description=__doc__)
    parser.parse_args()
    try:
        result = inspect_config(IntegrationConfig.load())
    except (OSError, ValueError, DecimalException):
        result = {'status': 'BLOCKED', 'blockers': ['invalid_or_unreadable_profile'],
                  'live_call_allowed': False, 'final_owner_approval_verified': False,
                  'remote_state_verified': False, 'provider_hard_cap_verified': False,
                  'external_calls': 0, 'credential_values_read': False}
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'LOCAL_CHECKS_PASSED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
