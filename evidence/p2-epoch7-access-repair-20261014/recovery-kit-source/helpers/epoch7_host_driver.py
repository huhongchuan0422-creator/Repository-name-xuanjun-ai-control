"""Finite composition of concrete epoch7 effects. No CLI or loader/admission default.

This module does not fabricate missing policy, host observations or approval. A
protected, source-authenticated loader must supply the full reviewed components.
"""
from epoch7_recovery_sequence import InjectedDriver, EXTERNAL_PHASES
from epoch7_host_phases import (CoreHostPhases, HostPhaseFilesystem, need)
from epoch7_exact_access import ExactAccessApplier
from epoch7_host_containment import BoundLegacyFiles, HostContainment, services_with_gateway
from epoch7_runtime_effects import Epoch7RuntimeEffects
from epoch7_runtime_acceptance import RuntimeAcceptanceChecks


def compose_driver(gate, controls, core, runtime, access, legacy, containment,
                   outer_io, retained_io, diagnostics, payloads, identity_payloads):
    need(isinstance(core, CoreHostPhases) and isinstance(runtime, Epoch7RuntimeEffects) and
         isinstance(access, ExactAccessApplier) and isinstance(legacy, BoundLegacyFiles) and
         isinstance(containment, HostContainment) and isinstance(outer_io, HostPhaseFilesystem),
         'CONCRETE_EFFECT_ADAPTERS_REQUIRED')
    need(len(gate.additions) == 2 and len(gate.delta['changes']) == 24,
         'EXACT24_PLUS_TWO_REVIEWED_TARGETS')
    need(core.io is outer_io and access.io is outer_io and legacy.io is outer_io and
         containment.io is outer_io and containment.core is core and containment.runtime is runtime and
         containment.legacy is legacy and runtime.diagnostics is diagnostics and
         legacy.diagnostics is diagnostics, 'ONE_CLAIM_AND_DIAGNOSTICS_COMPOSITION')
    need(getattr(runtime,'legacy',None) is legacy,'CONCRETE_SHARED_GATEWAY_RESTORE_REQUIRED')
    acceptance=getattr(runtime.access_check,'__self__',None)
    need(isinstance(acceptance,RuntimeAcceptanceChecks) and
         getattr(runtime.postcheck,'__self__',None) is acceptance and
         runtime.access_check.__func__ is RuntimeAcceptanceChecks.verify_runtime_access and
         runtime.postcheck.__func__ is RuntimeAcceptanceChecks.post_install_checks and
         acceptance.context == core.context and acceptance.diagnostics is diagnostics,
         'CONCRETE_SHARED_RUNTIME_ACCEPTANCE_REQUIRED')
    handlers = core.handlers()
    for phase in ('apply_fresh_sandbox','install_verified_plugin','reopen_existing_database',
                  'verify_runtime_access','post_install_checks'):
        handlers[phase] = getattr(runtime,phase)
    handlers['activate_new_services'] = services_with_gateway(legacy,runtime)
    handlers['apply_reviewed_access'] = access
    need(set(handlers) == EXTERNAL_PHASES, 'COMPLETE_FIXED_PHASE_SET')
    driver = InjectedDriver(gate,controls,outer_io,retained_io,handlers,containment,
                            diagnostics,payloads,identity_payloads)
    need(driver.context == core.context == runtime.context == access.context ==
         legacy.context == containment.context == outer_io.authority.context,
         'ALL_EFFECT_CONTEXTS_MUST_MATCH')
    return driver
