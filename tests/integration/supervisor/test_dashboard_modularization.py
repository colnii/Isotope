from __future__ import annotations

import isotope.features.supervisor.commands.dashboard as command_dashboard
import isotope.features.supervisor.state.snapshot_display as command_snapshot_display
import isotope.features.supervisor.dashboard._presentation as dashboard_presentation
import isotope.features.supervisor.state.snapshot_display as state_snapshot_display


def test_dashboard_command_module_reexports_dashboard_presentation():
    assert command_dashboard.handle_dashboard_command is dashboard_presentation.handle_dashboard_command
    assert command_dashboard.dashboard_payload is dashboard_presentation.dashboard_payload
    assert command_dashboard.print_dashboard_plain is dashboard_presentation.print_dashboard_plain


def test_snapshot_display_command_module_reexports_state_helpers():
    assert (
        command_snapshot_display.state_snapshot_schema_display
        is state_snapshot_display.state_snapshot_schema_display
    )
    assert (
        command_snapshot_display.state_snapshot_schema_status
        is state_snapshot_display.state_snapshot_schema_status
    )
