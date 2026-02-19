"""Tests for LangGraph workflow."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from src.workflow.graph import (
    create_ai_workflow,
    should_approve_signals,
    should_proceed_to_technical,
)
from src.workflow.nodes import (
    event_publishing_node,
    initialize_analysis,
    macro_analysis_node,
    risk_assessment_node,
    signal_generation_node,
    technical_analysis_node,
)
from src.workflow.state import (
    AnalysisState,
    MarketContext,
    RiskAssessment,
    TechnicalSignal,
    WorkflowPhase,
)


class TestWorkflowNodes:
    """Tests for individual workflow nodes."""

    @pytest.mark.asyncio
    async def test_initialize_analysis(self):
        """Test workflow initialization."""
        state: AnalysisState = {
            "user_id": "test_user",
            "stock_picks": [],
            "preferences": {},
            "phase": WorkflowPhase.INIT,
            "market_context": None,
            "technical_signals": [],
            "risk_assessment": None,
            "trading_signals": [],
            "analysis_id": "",
            "started_at": "",
            "errors": [],
        }

        result = await initialize_analysis(state)

        assert "analysis_id" in result
        assert "started_at" in result
        assert result["phase"] == WorkflowPhase.MACRO_ANALYSIS
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_macro_analysis_node_success(self):
        """Test macro analysis node with success."""
        state: AnalysisState = {
            "user_id": "test_user",
            "stock_picks": [{"symbol": "AAPL", "sector": "Technology"}],
            "preferences": {"regime": "normal_bull"},
            "phase": WorkflowPhase.MACRO_ANALYSIS,
            "market_context": None,
            "technical_signals": [],
            "risk_assessment": None,
            "trading_signals": [],
            "analysis_id": "test_id",
            "started_at": "2024-01-01",
            "errors": [],
        }

        with patch("src.workflow.nodes.get_macro_strategist") as mock_get:
            mock_strategist = AsyncMock()
            mock_strategist.analyze = AsyncMock(
                return_value=MarketContext(
                    regime="normal_bull",
                    confidence=0.8,
                    risk_level="medium",
                    sector_outlook={"Technology": 75},
                    macro_indicators={},
                )
            )
            mock_get.return_value = mock_strategist

            result = await macro_analysis_node(state)

            assert "market_context" in result
            assert result["phase"] == WorkflowPhase.TECHNICAL_ANALYSIS
            assert not result.get("errors")

    @pytest.mark.asyncio
    async def test_technical_analysis_node_success(self):
        """Test technical analysis node with success."""
        state: AnalysisState = {
            "user_id": "test_user",
            "stock_picks": [{"symbol": "AAPL", "sector": "Technology"}],
            "preferences": {},
            "phase": WorkflowPhase.TECHNICAL_ANALYSIS,
            "market_context": MarketContext(
                regime="normal_bull",
                confidence=0.8,
                risk_level="medium",
                sector_outlook={},
                macro_indicators={},
            ),
            "technical_signals": [],
            "risk_assessment": None,
            "trading_signals": [],
            "analysis_id": "test_id",
            "started_at": "2024-01-01",
            "errors": [],
        }

        with patch("src.workflow.nodes.get_technical_analyst") as mock_get:
            mock_analyst = AsyncMock()
            mock_analyst.analyze = AsyncMock(
                return_value=[
                    TechnicalSignal(
                        symbol="AAPL",
                        direction="long",
                        strength=0.75,
                        entry_price=Decimal("150.00"),
                        indicators={},
                        rationale="Strong momentum",
                    )
                ]
            )
            mock_get.return_value = mock_analyst

            result = await technical_analysis_node(state)

            assert "technical_signals" in result
            assert len(result["technical_signals"]) == 1
            assert result["phase"] == WorkflowPhase.RISK_ASSESSMENT

    @pytest.mark.asyncio
    async def test_risk_assessment_node_success(self):
        """Test risk assessment node with success."""
        state: AnalysisState = {
            "user_id": "test_user",
            "stock_picks": [],
            "preferences": {},
            "phase": WorkflowPhase.RISK_ASSESSMENT,
            "market_context": MarketContext(
                regime="normal_bull",
                confidence=0.8,
                risk_level="medium",
                sector_outlook={},
                macro_indicators={},
            ),
            "technical_signals": [
                TechnicalSignal(
                    symbol="AAPL",
                    direction="long",
                    strength=0.75,
                    entry_price=Decimal("150.00"),
                    indicators={},
                    rationale="Test",
                )
            ],
            "risk_assessment": None,
            "trading_signals": [],
            "analysis_id": "test_id",
            "started_at": "2024-01-01",
            "errors": [],
        }

        with patch("src.workflow.nodes.get_risk_manager") as mock_get:
            mock_manager = AsyncMock()
            mock_manager.assess = AsyncMock(
                return_value=RiskAssessment(
                    approved=True,
                    risk_score=0.4,
                    position_adjustments={},
                    warnings=[],
                    concentration_risk=0.3,
                )
            )
            mock_get.return_value = mock_manager

            result = await risk_assessment_node(state)

            assert "risk_assessment" in result
            assert result["risk_assessment"].approved is True
            assert result["phase"] == WorkflowPhase.SIGNAL_GENERATION

    @pytest.mark.asyncio
    async def test_signal_generation_node(self):
        """Test signal generation node."""
        state: AnalysisState = {
            "user_id": "test_user",
            "stock_picks": [],
            "preferences": {"risk_profile": "MODERATE"},
            "phase": WorkflowPhase.SIGNAL_GENERATION,
            "market_context": MarketContext(
                regime="normal_bull",
                confidence=0.8,
                risk_level="medium",
                sector_outlook={},
                macro_indicators={},
            ),
            "technical_signals": [
                TechnicalSignal(
                    symbol="AAPL",
                    direction="long",
                    strength=0.75,
                    entry_price=Decimal("150.00"),
                    indicators={},
                    rationale="Test",
                )
            ],
            "risk_assessment": RiskAssessment(
                approved=True,
                risk_score=0.4,
                position_adjustments={},
                warnings=[],
                concentration_risk=0.3,
            ),
            "trading_signals": [],
            "analysis_id": "test_id",
            "started_at": "2024-01-01",
            "errors": [],
        }

        result = await signal_generation_node(state)

        assert "trading_signals" in result
        assert len(result["trading_signals"]) == 1
        assert result["phase"] == WorkflowPhase.EVENT_PUBLISHING

    @pytest.mark.asyncio
    async def test_event_publishing_node(self):
        """Test event publishing node."""
        from src.workflow.state import TradingSignal

        state: AnalysisState = {
            "user_id": "test_user",
            "stock_picks": [],
            "preferences": {},
            "phase": WorkflowPhase.EVENT_PUBLISHING,
            "market_context": MarketContext(
                regime="normal_bull",
                confidence=0.8,
                risk_level="medium",
                sector_outlook={},
                macro_indicators={},
            ),
            "technical_signals": [],
            "risk_assessment": None,
            "trading_signals": [
                TradingSignal(
                    symbol="AAPL",
                    action="buy",
                    confidence=0.75,
                    size_recommendation=Decimal("0.05"),
                    entry_price=Decimal("150.00"),
                    stop_loss=Decimal("147.00"),
                    take_profit=Decimal("157.50"),
                    rationale="Test",
                    risk_approved=True,
                )
            ],
            "analysis_id": "test_id",
            "started_at": "2024-01-01",
            "errors": [],
        }

        with patch("src.workflow.nodes.get_event_publisher") as mock_get:
            mock_publisher = AsyncMock()
            mock_publisher.publish_strategy_signal = AsyncMock()
            mock_publisher.publish_market_alert = AsyncMock()
            mock_get.return_value = mock_publisher

            result = await event_publishing_node(state)

            assert result["phase"] == WorkflowPhase.COMPLETE
            mock_publisher.publish_strategy_signal.assert_called_once()
            mock_publisher.publish_market_alert.assert_called_once()


class TestConditionalEdges:
    """Tests for workflow conditional edges."""

    def test_should_proceed_to_technical_success(self):
        """Test proceeding to technical analysis."""
        state: AnalysisState = {
            "user_id": "test_user",
            "stock_picks": [],
            "preferences": {},
            "phase": WorkflowPhase.MACRO_ANALYSIS,
            "market_context": MarketContext(
                regime="normal_bull",
                confidence=0.8,
                risk_level="medium",
                sector_outlook={},
                macro_indicators={},
            ),
            "technical_signals": [],
            "risk_assessment": None,
            "trading_signals": [],
            "analysis_id": "test_id",
            "started_at": "2024-01-01",
            "errors": [],
        }

        result = should_proceed_to_technical(state)
        assert result == "technical"

    def test_should_proceed_to_technical_extreme_risk(self):
        """Test aborting on extreme risk."""
        state: AnalysisState = {
            "user_id": "test_user",
            "stock_picks": [],
            "preferences": {},
            "phase": WorkflowPhase.MACRO_ANALYSIS,
            "market_context": MarketContext(
                regime="crisis",
                confidence=0.8,
                risk_level="extreme",
                sector_outlook={},
                macro_indicators={},
            ),
            "technical_signals": [],
            "risk_assessment": None,
            "trading_signals": [],
            "analysis_id": "test_id",
            "started_at": "2024-01-01",
            "errors": [],
        }

        result = should_proceed_to_technical(state)
        assert result == "error"

    def test_should_proceed_to_technical_with_errors(self):
        """Test aborting when errors present."""
        state: AnalysisState = {
            "user_id": "test_user",
            "stock_picks": [],
            "preferences": {},
            "phase": WorkflowPhase.MACRO_ANALYSIS,
            "market_context": None,
            "technical_signals": [],
            "risk_assessment": None,
            "trading_signals": [],
            "analysis_id": "test_id",
            "started_at": "2024-01-01",
            "errors": ["Macro analysis failed"],
        }

        result = should_proceed_to_technical(state)
        assert result == "error"

    def test_should_approve_signals_approved(self):
        """Test signal generation approval."""
        state: AnalysisState = {
            "user_id": "test_user",
            "stock_picks": [],
            "preferences": {},
            "phase": WorkflowPhase.RISK_ASSESSMENT,
            "market_context": None,
            "technical_signals": [],
            "risk_assessment": RiskAssessment(
                approved=True,
                risk_score=0.4,
                position_adjustments={},
                warnings=[],
                concentration_risk=0.3,
            ),
            "trading_signals": [],
            "analysis_id": "test_id",
            "started_at": "2024-01-01",
            "errors": [],
        }

        result = should_approve_signals(state)
        assert result == "generate"

    def test_should_approve_signals_rejected(self):
        """Test signal generation rejection."""
        state: AnalysisState = {
            "user_id": "test_user",
            "stock_picks": [],
            "preferences": {},
            "phase": WorkflowPhase.RISK_ASSESSMENT,
            "market_context": None,
            "technical_signals": [],
            "risk_assessment": RiskAssessment(
                approved=False,
                risk_score=0.9,
                position_adjustments={},
                warnings=["High risk"],
                concentration_risk=0.8,
            ),
            "trading_signals": [],
            "analysis_id": "test_id",
            "started_at": "2024-01-01",
            "errors": [],
        }

        result = should_approve_signals(state)
        assert result == "reject"


class TestWorkflowGraph:
    """Tests for complete workflow graph."""

    def test_create_ai_workflow(self):
        """Test workflow creation."""
        workflow = create_ai_workflow()
        assert workflow is not None

    @pytest.mark.asyncio
    async def test_workflow_execution_mock(self):
        """Test full workflow execution with mocks."""
        workflow = create_ai_workflow()

        initial_state: AnalysisState = {
            "user_id": "test_user",
            "stock_picks": [{"symbol": "AAPL", "sector": "Technology"}],
            "preferences": {"regime": "normal_bull", "risk_profile": "MODERATE"},
            "phase": WorkflowPhase.INIT,
            "market_context": None,
            "technical_signals": [],
            "risk_assessment": None,
            "trading_signals": [],
            "analysis_id": "",
            "started_at": "",
            "errors": [],
        }

        # Mock all agents
        with patch("src.workflow.nodes.get_macro_strategist") as mock_macro, \
             patch("src.workflow.nodes.get_technical_analyst") as mock_tech, \
             patch("src.workflow.nodes.get_risk_manager") as mock_risk, \
             patch("src.workflow.nodes.get_event_publisher") as mock_pub:

            # Setup mocks
            mock_macro.return_value.analyze = AsyncMock(
                return_value=MarketContext(
                    regime="normal_bull",
                    confidence=0.8,
                    risk_level="medium",
                    sector_outlook={"Technology": 75},
                    macro_indicators={},
                )
            )

            mock_tech.return_value.analyze = AsyncMock(
                return_value=[
                    TechnicalSignal(
                        symbol="AAPL",
                        direction="long",
                        strength=0.75,
                        entry_price=Decimal("150.00"),
                        indicators={},
                        rationale="Test",
                    )
                ]
            )

            mock_risk.return_value.assess = AsyncMock(
                return_value=RiskAssessment(
                    approved=True,
                    risk_score=0.4,
                    position_adjustments={},
                    warnings=[],
                    concentration_risk=0.3,
                )
            )

            mock_pub.return_value.publish_strategy_signal = AsyncMock()
            mock_pub.return_value.publish_market_alert = AsyncMock()

            # Execute workflow
            final_state = await workflow.ainvoke(initial_state)

            # Verify final state
            assert final_state["phase"] == WorkflowPhase.COMPLETE
            assert len(final_state["trading_signals"]) == 1
            assert final_state["trading_signals"][0].symbol == "AAPL"


class TestWorkflowNodesErrorHandling:
    """Tests for workflow nodes error handling paths."""

    @pytest.mark.asyncio
    async def test_macro_analysis_node_error(self):
        """Test macro analysis node error handling."""
        state: AnalysisState = {
            "user_id": "test_user",
            "stock_picks": [{"symbol": "AAPL", "sector": "Technology"}],
            "preferences": {"regime": "normal_bull"},
            "phase": WorkflowPhase.MACRO_ANALYSIS,
            "market_context": None,
            "technical_signals": [],
            "risk_assessment": None,
            "trading_signals": [],
            "analysis_id": "test_id",
            "started_at": "2024-01-01",
            "errors": [],
        }

        with patch("src.workflow.nodes.get_macro_strategist") as mock_get:
            mock_strategist = AsyncMock()
            mock_strategist.analyze = AsyncMock(side_effect=Exception("Claude API error"))
            mock_get.return_value = mock_strategist

            result = await macro_analysis_node(state)

            assert result["phase"] == WorkflowPhase.ERROR
            assert len(result["errors"]) == 1
            assert "Macro analysis error" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_technical_analysis_node_error(self):
        """Test technical analysis node error handling."""
        state: AnalysisState = {
            "user_id": "test_user",
            "stock_picks": [{"symbol": "AAPL", "sector": "Technology"}],
            "preferences": {},
            "phase": WorkflowPhase.TECHNICAL_ANALYSIS,
            "market_context": MarketContext(
                regime="normal_bull",
                confidence=0.8,
                risk_level="medium",
                sector_outlook={},
                macro_indicators={},
            ),
            "technical_signals": [],
            "risk_assessment": None,
            "trading_signals": [],
            "analysis_id": "test_id",
            "started_at": "2024-01-01",
            "errors": [],
        }

        with patch("src.workflow.nodes.get_technical_analyst") as mock_get:
            mock_analyst = AsyncMock()
            mock_analyst.analyze = AsyncMock(side_effect=Exception("Claude API error"))
            mock_get.return_value = mock_analyst

            result = await technical_analysis_node(state)

            assert result["phase"] == WorkflowPhase.ERROR
            assert len(result["errors"]) == 1
            assert "Technical analysis error" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_technical_analysis_node_preserves_existing_errors(self):
        """Test technical analysis node preserves existing errors."""
        state: AnalysisState = {
            "user_id": "test_user",
            "stock_picks": [{"symbol": "AAPL", "sector": "Technology"}],
            "preferences": {},
            "phase": WorkflowPhase.TECHNICAL_ANALYSIS,
            "market_context": MarketContext(
                regime="normal_bull",
                confidence=0.8,
                risk_level="medium",
                sector_outlook={},
                macro_indicators={},
            ),
            "technical_signals": [],
            "risk_assessment": None,
            "trading_signals": [],
            "analysis_id": "test_id",
            "started_at": "2024-01-01",
            "errors": ["Previous error"],
        }

        with patch("src.workflow.nodes.get_technical_analyst") as mock_get:
            mock_analyst = AsyncMock()
            mock_analyst.analyze = AsyncMock(side_effect=Exception("Claude API error"))
            mock_get.return_value = mock_analyst

            result = await technical_analysis_node(state)

            assert result["phase"] == WorkflowPhase.ERROR
            assert len(result["errors"]) == 2
            assert "Previous error" in result["errors"]
            assert "Technical analysis error" in result["errors"][1]

    @pytest.mark.asyncio
    async def test_risk_assessment_node_error(self):
        """Test risk assessment node error handling."""
        state: AnalysisState = {
            "user_id": "test_user",
            "stock_picks": [],
            "preferences": {},
            "phase": WorkflowPhase.RISK_ASSESSMENT,
            "market_context": MarketContext(
                regime="normal_bull",
                confidence=0.8,
                risk_level="medium",
                sector_outlook={},
                macro_indicators={},
            ),
            "technical_signals": [
                TechnicalSignal(
                    symbol="AAPL",
                    direction="long",
                    strength=0.75,
                    entry_price=Decimal("150.00"),
                    indicators={},
                    rationale="Test",
                )
            ],
            "risk_assessment": None,
            "trading_signals": [],
            "analysis_id": "test_id",
            "started_at": "2024-01-01",
            "errors": [],
        }

        with patch("src.workflow.nodes.get_risk_manager") as mock_get:
            mock_manager = AsyncMock()
            mock_manager.assess = AsyncMock(side_effect=Exception("Risk assessment failed"))
            mock_get.return_value = mock_manager

            result = await risk_assessment_node(state)

            assert result["phase"] == WorkflowPhase.ERROR
            assert len(result["errors"]) == 1
            assert "Risk assessment error" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_signal_generation_node_error(self):
        """Test signal generation node error handling."""
        from unittest.mock import Mock

        state: AnalysisState = {
            "user_id": "test_user",
            "stock_picks": [],
            "preferences": {"risk_profile": "MODERATE"},
            "phase": WorkflowPhase.SIGNAL_GENERATION,
            "market_context": MarketContext(
                regime="normal_bull",
                confidence=0.8,
                risk_level="medium",
                sector_outlook={},
                macro_indicators={},
            ),
            "technical_signals": [
                TechnicalSignal(
                    symbol="AAPL",
                    direction="long",
                    strength=0.75,
                    entry_price=Decimal("150.00"),
                    indicators={},
                    rationale="Test",
                )
            ],
            "risk_assessment": RiskAssessment(
                approved=True,
                risk_score=0.4,
                position_adjustments={},
                warnings=[],
                concentration_risk=0.3,
            ),
            "trading_signals": [],
            "analysis_id": "test_id",
            "started_at": "2024-01-01",
            "errors": [],
        }

        with patch("src.workflow.nodes.get_signal_generator") as mock_get:
            mock_generator = Mock()
            mock_generator.generate.side_effect = Exception("Signal generation failed")
            mock_get.return_value = mock_generator

            result = await signal_generation_node(state)

            assert result["phase"] == WorkflowPhase.ERROR
            assert len(result["errors"]) == 1
            assert "Signal generation error" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_event_publishing_node_error(self):
        """Test event publishing node error handling."""
        from src.workflow.state import TradingSignal

        state: AnalysisState = {
            "user_id": "test_user",
            "stock_picks": [],
            "preferences": {},
            "phase": WorkflowPhase.EVENT_PUBLISHING,
            "market_context": MarketContext(
                regime="normal_bull",
                confidence=0.8,
                risk_level="medium",
                sector_outlook={},
                macro_indicators={},
            ),
            "technical_signals": [],
            "risk_assessment": None,
            "trading_signals": [
                TradingSignal(
                    symbol="AAPL",
                    action="buy",
                    confidence=0.75,
                    size_recommendation=Decimal("0.05"),
                    entry_price=Decimal("150.00"),
                    stop_loss=Decimal("147.00"),
                    take_profit=Decimal("157.50"),
                    rationale="Test",
                    risk_approved=True,
                )
            ],
            "analysis_id": "test_id",
            "started_at": "2024-01-01",
            "errors": [],
        }

        with patch("src.workflow.nodes.get_event_publisher") as mock_get:
            mock_publisher = AsyncMock()
            mock_publisher.publish_strategy_signal = AsyncMock(
                side_effect=Exception("Redpanda connection error")
            )
            mock_get.return_value = mock_publisher

            result = await event_publishing_node(state)

            assert result["phase"] == WorkflowPhase.ERROR
            assert len(result["errors"]) == 1
            assert "Event publishing error" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_event_publishing_node_preserves_existing_errors(self):
        """Test event publishing node preserves existing errors."""
        from src.workflow.state import TradingSignal

        state: AnalysisState = {
            "user_id": "test_user",
            "stock_picks": [],
            "preferences": {},
            "phase": WorkflowPhase.EVENT_PUBLISHING,
            "market_context": MarketContext(
                regime="normal_bull",
                confidence=0.8,
                risk_level="medium",
                sector_outlook={},
                macro_indicators={},
            ),
            "technical_signals": [],
            "risk_assessment": None,
            "trading_signals": [
                TradingSignal(
                    symbol="AAPL",
                    action="buy",
                    confidence=0.75,
                    size_recommendation=Decimal("0.05"),
                    entry_price=Decimal("150.00"),
                    stop_loss=Decimal("147.00"),
                    take_profit=Decimal("157.50"),
                    rationale="Test",
                    risk_approved=True,
                )
            ],
            "analysis_id": "test_id",
            "started_at": "2024-01-01",
            "errors": ["Previous warning"],
        }

        with patch("src.workflow.nodes.get_event_publisher") as mock_get:
            mock_publisher = AsyncMock()
            mock_publisher.publish_strategy_signal = AsyncMock(
                side_effect=Exception("Redpanda error")
            )
            mock_get.return_value = mock_publisher

            result = await event_publishing_node(state)

            assert result["phase"] == WorkflowPhase.ERROR
            assert len(result["errors"]) == 2
            assert "Previous warning" in result["errors"]


class TestSingletonGetters:
    """Tests for singleton getter functions in nodes."""

    def test_get_macro_strategist_singleton(self):
        """Test that get_macro_strategist creates singleton."""
        from src.workflow import nodes

        # Reset the singleton
        nodes._macro_strategist = None

        with patch("src.workflow.nodes.MacroStrategist") as mock_class:
            mock_instance = AsyncMock()
            mock_class.return_value = mock_instance

            # First call should create instance
            result1 = nodes.get_macro_strategist()

            # Second call should return same instance
            result2 = nodes.get_macro_strategist()

            assert result1 is result2
            mock_class.assert_called_once()

        # Reset for other tests
        nodes._macro_strategist = None

    def test_get_technical_analyst_singleton(self):
        """Test that get_technical_analyst creates singleton."""
        from src.workflow import nodes

        # Reset the singleton
        nodes._technical_analyst = None

        with patch("src.workflow.nodes.TechnicalAnalyst") as mock_class:
            mock_instance = AsyncMock()
            mock_class.return_value = mock_instance

            # First call should create instance
            result1 = nodes.get_technical_analyst()

            # Second call should return same instance
            result2 = nodes.get_technical_analyst()

            assert result1 is result2
            mock_class.assert_called_once()

        # Reset for other tests
        nodes._technical_analyst = None

    def test_get_risk_manager_singleton(self):
        """Test that get_risk_manager creates singleton."""
        from src.workflow import nodes

        # Reset the singleton
        nodes._risk_manager = None

        with patch("src.workflow.nodes.RiskManager") as mock_class:
            mock_instance = AsyncMock()
            mock_class.return_value = mock_instance

            # First call should create instance
            result1 = nodes.get_risk_manager()

            # Second call should return same instance
            result2 = nodes.get_risk_manager()

            assert result1 is result2
            mock_class.assert_called_once()

        # Reset for other tests
        nodes._risk_manager = None

    def test_get_signal_generator_singleton(self):
        """Test that get_signal_generator creates singleton."""
        from src.workflow import nodes

        # Reset the singleton
        nodes._signal_generator = None

        with patch("src.workflow.nodes.SignalGenerator") as mock_class:
            mock_instance = AsyncMock()
            mock_class.return_value = mock_instance

            # First call should create instance
            result1 = nodes.get_signal_generator()

            # Second call should return same instance
            result2 = nodes.get_signal_generator()

            assert result1 is result2
            mock_class.assert_called_once()

        # Reset for other tests
        nodes._signal_generator = None

    def test_get_event_publisher_singleton(self):
        """Test that get_event_publisher creates singleton."""
        from src.workflow import nodes

        # Reset the singleton
        nodes._event_publisher = None

        with patch("src.workflow.nodes.RedpandaClient"), \
             patch("src.workflow.nodes.EventPublisher") as mock_class:
            mock_instance = AsyncMock()
            mock_class.return_value = mock_instance

            # First call should create instance
            result1 = nodes.get_event_publisher()

            # Second call should return same instance
            result2 = nodes.get_event_publisher()

            assert result1 is result2
            mock_class.assert_called_once()

        # Reset for other tests
        nodes._event_publisher = None
