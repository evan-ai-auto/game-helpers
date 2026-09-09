"""Regression tests for package import boundaries."""


def test_capture_models_import_without_initializing_capture_backends():
    from game_helpers.capture.models import Frame

    assert Frame is not None


def test_runtime_imports_without_capture_tasks_cycle():
    from game_helpers.runtime import AgentRuntime

    assert AgentRuntime is not None
