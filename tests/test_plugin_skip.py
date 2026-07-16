from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

from nomad_plugin_tests.plugin_selection import (
    PluginIdentity,
    parse_plugin_skip_list,
    resolve_skip_selectors,
)


ROOT = Path(__file__).parents[1]


def test_selector_contract_does_not_drift():
    plugins = (
        PluginIdentity("alpha_schema", "nomad-example"),
        PluginIdentity("beta_parser", "nomad-example"),
        PluginIdentity("missing_metadata", None),
    )

    resolution = resolve_skip_selectors(
        parse_plugin_skip_list("Nomad_Example unknown"), plugins
    )

    assert resolution.matched == plugins[:2]
    assert resolution.unknown == ("unknown",)
    assert resolve_skip_selectors(("ALPHA_SCHEMA",), plugins).unknown == (
        "ALPHA_SCHEMA",
    )
    assert resolve_skip_selectors(("MISSING-METADATA",), plugins).unknown == (
        "MISSING-METADATA",
    )


def test_workflow_passes_one_scalar_unchanged_and_uses_locked_tools():
    workflow = (ROOT / ".github/workflows/docker-publish.yml").read_text()

    assert "PLUGINS_STRING" not in workflow
    assert "tr '\\n'" not in workflow
    assert "--with" not in workflow
    assert '--plugins-to-skip "$PLUGIN_TESTS_PLUGINS_TO_SKIP"' in workflow
    assert "--group test" in workflow
    assert "--frozen" in workflow
    assert "uv sync --frozen --extra plugins --group test" in workflow


def test_selector_tool_is_immutably_pinned_and_present_in_lock():
    with (ROOT / "pyproject.toml").open("rb") as file:
        pyproject = tomllib.load(file)
    requirement = next(
        item
        for item in pyproject["dependency-groups"]["test"]
        if item.startswith("nomad-plugin-tests @ git+")
    )
    pinned_commit = requirement.rpartition("@")[2]

    with (ROOT / "uv.lock").open("rb") as file:
        lock = tomllib.load(file)
    locked_packages = [
        package
        for package in lock["package"]
        if package["name"] == "nomad-plugin-tests"
    ]

    assert len(pinned_commit) == 40
    assert len(locked_packages) == 1
    assert locked_packages[0]["version"] == "0.3.0"
    assert locked_packages[0]["source"] == {
        "git": "https://github.com/QEDeD/nomad-plugin-tests.git"
        f"?rev={pinned_commit}#{pinned_commit}"
    }


def test_example_selection_is_runtime_scoped_and_uses_shared_exact_matcher():
    source = (ROOT / "tests/test_example_uploads.py").read_text()

    assert "@pytest.mark.parametrize" in source
    assert "def example_upload_ids" not in source
    assert "plugin_module_is_skipped" in source
    assert "select_identities_by_module" in source
    assert "format_requested_and_matched" in source
    assert "format_actually_skipped" in source
    assert "PLUGIN_TESTS_PLUGINS_TO_SKIP" in source
    assert "PLUGINS_STRING" not in source


def test_nomad_client_still_initializes_before_configuration():
    conftest_source = (ROOT / "tests/conftest.py").read_text()
    example_source = (ROOT / "tests/test_example_uploads.py").read_text()

    assert "def get_nomad_api" in conftest_source
    assert example_source.index("get_nomad_api()") < example_source.index(
        "config.load_plugins()"
    )


def test_example_reporting_is_module_scoped_and_precedes_plugin_loading():
    conftest_source = (ROOT / "tests/conftest.py").read_text()
    source = (ROOT / "tests/test_example_uploads.py").read_text()
    selection_source = source[
        source.index("def get_example_upload_ids") : source.index(
            "@pytest.mark.parametrize"
        )
    ]

    assert "pytest_sessionstart" not in conftest_source
    assert "PLUGIN_TESTS_PLUGINS_TO_SKIP" not in conftest_source
    assert selection_source.index("if resolution.unknown") < selection_source.index(
        "get_example_upload_entrypoints()"
    )
    assert selection_source.index(
        "format_requested_and_matched"
    ) < selection_source.index("get_example_upload_entrypoints()")
    assert selection_source.index(
        "get_example_upload_entrypoints()"
    ) < selection_source.index("format_actually_skipped")
