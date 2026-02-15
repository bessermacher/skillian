"""Tests for data_availability skill."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.skill_loader import SkillLoader
from app.skills.data_availability import tools as availability_tools
from app.skills.data_availability.source_config import (
    InvestigationSourceConfig,
    load_investigation_config,
)

# --- Fixtures ---


@pytest.fixture
def mock_connector():
    """Mock Datasphere connector."""
    connector = MagicMock()
    connector.space = "TEST_SPACE"
    connector.execute_sql = AsyncMock(return_value=[])
    return connector


@pytest.fixture
def skill_loader(mock_connector):
    """Create skill loader with mock connector."""
    return SkillLoader(
        skills_dir=Path("app/skills"),
        connector_factory={"datasphere": mock_connector},
    )


@pytest.fixture
def skill(skill_loader):
    """Load the data_availability skill."""
    return skill_loader.load_skill("data_availability")


@pytest.fixture(autouse=True)
def reset_module_state(mock_connector):
    """Reset module-level state between tests."""
    availability_tools._connector = mock_connector
    availability_tools._source_config = None
    yield
    availability_tools._connector = None
    availability_tools._source_config = None


# --- Skill Loading Tests ---


class TestDataAvailabilitySkill:
    def test_skill_name(self, skill):
        assert skill.name == "data-availability"

    def test_skill_description(self, skill):
        assert "availability" in skill.description.lower()

    def test_skill_has_tools(self, skill):
        assert len(skill.tools) == 2

    def test_tool_names(self, skill):
        tool_names = [t.name for t in skill.tools]
        assert "list_investigation_sources" in tool_names
        assert "check_data_availability" in tool_names

    def test_system_prompt_not_empty(self, skill):
        assert len(skill.system_prompt) > 100

    def test_connector_type(self, skill):
        assert skill.connector_type == "datasphere"


# --- Source Config Tests ---


class TestSourceConfig:
    def test_load_config(self):
        config = load_investigation_config(Path("config/investigation_sources.yaml"))
        assert isinstance(config, InvestigationSourceConfig)
        assert config.schema_name == "BW2AI"

    def test_reports_loaded(self):
        config = load_investigation_config(Path("config/investigation_sources.yaml"))
        assert "consolidation_management" in config.reports
        report = config.reports["consolidation_management"]
        assert len(report.versions) == 5

    def test_tables_loaded(self):
        config = load_investigation_config(Path("config/investigation_sources.yaml"))
        assert "bpc_mart" in config.tables
        assert config.tables["bpc_mart"].table == "CV_ZFI_AA01"

    def test_scope_values_loaded(self):
        config = load_investigation_config(Path("config/investigation_sources.yaml"))
        assert "S_NONE" in config.scope_values
        assert "S_LEGAL" in config.scope_values

    def test_get_table_info_from_report(self):
        config = load_investigation_config(Path("config/investigation_sources.yaml"))
        info = config.get_table_info("CV_ZBC_AA61")
        assert info is not None
        assert info["source_name"] == "consolidation_management"
        assert info["source_type"] == "report"
        assert len(info["default_group_by"]) > 0

    def test_get_table_info_from_tables(self):
        config = load_investigation_config(Path("config/investigation_sources.yaml"))
        info = config.get_table_info("CV_ZFI_AA01")
        assert info is not None
        assert info["source_name"] == "bpc_mart"
        assert info["source_type"] == "table"

    def test_get_table_info_not_found(self):
        config = load_investigation_config(Path("config/investigation_sources.yaml"))
        info = config.get_table_info("NONEXISTENT_TABLE")
        assert info is None

    def test_get_all_table_names(self):
        config = load_investigation_config(Path("config/investigation_sources.yaml"))
        tables = config.get_all_table_names()
        assert "CV_ZBC_AA61" in tables
        assert "CV_ZBC_AA62" in tables
        assert "CV_ZFI_AA01" in tables
        assert "CV_ZBC_AA08Z" in tables

    def test_missing_config_file(self):
        with pytest.raises(FileNotFoundError):
            load_investigation_config(Path("nonexistent.yaml"))

    def test_dimension_aliases(self):
        config = load_investigation_config(Path("config/investigation_sources.yaml"))
        report = config.reports["consolidation_management"]
        company_dim = next(d for d in report.check_dimensions if d.column == "/BIC/ZCOMPCODE")
        assert "cocd" in company_dim.aliases
        assert "company_code" in company_dim.aliases


# --- Tool Function Tests ---


class TestListInvestigationSources:
    def test_returns_reports(self, mock_connector):
        result = availability_tools.list_investigation_sources(connector=mock_connector)
        assert "reports" in result
        assert len(result["reports"]) > 0
        report = result["reports"][0]
        assert "name" in report
        assert "versions" in report
        assert "check_dimensions" in report

    def test_returns_tables(self, mock_connector):
        result = availability_tools.list_investigation_sources(connector=mock_connector)
        assert "tables" in result
        assert len(result["tables"]) > 0

    def test_returns_scope_values(self, mock_connector):
        result = availability_tools.list_investigation_sources(connector=mock_connector)
        assert "scope_values" in result
        assert "S_NONE" in result["scope_values"]

    def test_returns_all_table_names(self, mock_connector):
        result = availability_tools.list_investigation_sources(connector=mock_connector)
        assert "all_table_names" in result
        assert "CV_ZBC_AA61" in result["all_table_names"]


class TestCheckDataAvailability:
    @pytest.mark.asyncio
    async def test_data_found(self, mock_connector):
        mock_connector.execute_sql = AsyncMock(
            return_value=[
                {
                    "/BIC/ZCOMPCODE": "1110",
                    "/BIC/ZVERSION": "001",
                    "FISCPER": "2024012",
                    "/BIC/ZSCOPE": "S_LEGAL",
                    "ROW_COUNT": 42,
                },
            ]
        )

        result = await availability_tools.check_data_availability(
            table="CV_ZBC_AA61",
            filters={"/BIC/ZCOMPCODE": "1110", "FISCPER": "2024012"},
            connector=mock_connector,
        )

        assert result["data_found"] is True
        assert result["total_rows"] == 42
        assert result["group_count"] == 1
        assert len(result["groups"]) == 1

    @pytest.mark.asyncio
    async def test_no_data_found(self, mock_connector):
        mock_connector.execute_sql = AsyncMock(return_value=[])

        result = await availability_tools.check_data_availability(
            table="CV_ZBC_AA61",
            filters={"/BIC/ZCOMPCODE": "9999"},
            connector=mock_connector,
        )

        assert result["data_found"] is False
        assert result["total_rows"] == 0
        assert result["groups"] == []

    @pytest.mark.asyncio
    async def test_with_filters(self, mock_connector):
        mock_connector.execute_sql = AsyncMock(return_value=[])

        await availability_tools.check_data_availability(
            table="CV_ZBC_AA61",
            filters={"/BIC/ZCOMPCODE": "1110", "FISCPER": "2024012"},
            connector=mock_connector,
        )

        call_args = mock_connector.execute_sql.call_args[0][0]
        assert "\"/BIC/ZCOMPCODE\" = '1110'" in call_args
        assert "\"FISCPER\" = '2024012'" in call_args

    @pytest.mark.asyncio
    async def test_default_group_by(self, mock_connector):
        mock_connector.execute_sql = AsyncMock(return_value=[])

        result = await availability_tools.check_data_availability(
            table="CV_ZBC_AA61",
            connector=mock_connector,
        )

        # Should use default group_by from config
        assert "/BIC/ZCOMPCODE" in result["group_by"]
        assert "/BIC/ZVERSION" in result["group_by"]

    @pytest.mark.asyncio
    async def test_custom_group_by(self, mock_connector):
        mock_connector.execute_sql = AsyncMock(return_value=[])

        result = await availability_tools.check_data_availability(
            table="CV_ZBC_AA61",
            group_by=["/BIC/ZCOMPCODE"],
            connector=mock_connector,
        )

        assert result["group_by"] == ["/BIC/ZCOMPCODE"]
        call_args = mock_connector.execute_sql.call_args[0][0]
        assert "GROUP BY" in call_args

    @pytest.mark.asyncio
    async def test_sql_error_handling(self, mock_connector):
        from app.connectors.datasphere import DatasphereQueryError

        mock_connector.execute_sql = AsyncMock(side_effect=DatasphereQueryError("Connection lost"))

        result = await availability_tools.check_data_availability(
            table="CV_ZBC_AA61",
            connector=mock_connector,
        )

        assert "error" in result
        assert result["data_found"] is False

    @pytest.mark.asyncio
    async def test_invalid_table_name(self, mock_connector):
        result = await availability_tools.check_data_availability(
            table="DROP TABLE; --",
            connector=mock_connector,
        )

        assert "error" in result
        assert result["data_found"] is False
        mock_connector.execute_sql.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_filter_column(self, mock_connector):
        result = await availability_tools.check_data_availability(
            table="CV_ZBC_AA61",
            filters={"'; DROP TABLE --": "bad"},
            connector=mock_connector,
        )

        assert "error" in result
        assert result["data_found"] is False
        mock_connector.execute_sql.assert_not_called()

    @pytest.mark.asyncio
    async def test_query_includes_schema(self, mock_connector):
        mock_connector.execute_sql = AsyncMock(return_value=[])

        await availability_tools.check_data_availability(
            table="CV_ZBC_AA61",
            connector=mock_connector,
        )

        call_args = mock_connector.execute_sql.call_args[0][0]
        assert '"BW2AI"' in call_args
        assert '"CV_ZBC_AA61"' in call_args

    @pytest.mark.asyncio
    async def test_filters_applied_in_result(self, mock_connector):
        mock_connector.execute_sql = AsyncMock(return_value=[])
        filters = {"/BIC/ZCOMPCODE": "1110"}

        result = await availability_tools.check_data_availability(
            table="CV_ZBC_AA61",
            filters=filters,
            connector=mock_connector,
        )

        assert result["filters_applied"] == filters
