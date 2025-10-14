"""
Tests for all enum classes in the schemas package.
"""
import pytest
from schemas import (
    TaskPriority,
    TaskStatus,
    EntityType,
    AgentType,
    WorkerType,
)


class TestTaskPriority:
    """Test cases for TaskPriority enum."""
    
    def test_enum_values(self):
        """Test that TaskPriority has correct values."""
        assert TaskPriority.LOW.value == 1
        assert TaskPriority.MEDIUM.value == 2
        assert TaskPriority.HIGH.value == 3
    
    def test_enum_members(self):
        """Test that all expected members exist."""
        expected_members = {"LOW", "MEDIUM", "HIGH"}
        actual_members = {member.name for member in TaskPriority}
        assert actual_members == expected_members
    
    def test_enum_comparison(self):
        """Test enum comparison operations."""
        # Test value comparison
        assert TaskPriority.LOW.value < TaskPriority.MEDIUM.value
        assert TaskPriority.MEDIUM.value < TaskPriority.HIGH.value
        assert TaskPriority.LOW.value < TaskPriority.HIGH.value
        
        # Test equality
        assert TaskPriority.LOW == TaskPriority.LOW
        assert TaskPriority.LOW != TaskPriority.MEDIUM
    
    def test_enum_string_representation(self):
        """Test string representation of enum values."""
        assert str(TaskPriority.LOW) == "TaskPriority.LOW"
        assert repr(TaskPriority.HIGH) == "<TaskPriority.HIGH: 3>"


class TestTaskStatus:
    """Test cases for TaskStatus enum."""
    
    def test_enum_values(self):
        """Test that TaskStatus has correct string values."""
        assert TaskStatus.SUCCESS.value == "SUCCESS"
        assert TaskStatus.FAILURE.value == "FAILURE"
        assert TaskStatus.ESCALATED.value == "ESCALATED_TO_HUMAN"
    
    def test_enum_members(self):
        """Test that all expected members exist."""
        expected_members = {"SUCCESS", "FAILURE", "ESCALATED"}
        actual_members = {member.name for member in TaskStatus}
        assert actual_members == expected_members
    
    def test_enum_equality(self):
        """Test enum equality operations."""
        assert TaskStatus.SUCCESS == TaskStatus.SUCCESS
        assert TaskStatus.SUCCESS != TaskStatus.FAILURE


class TestEntityType:
    """Test cases for EntityType enum."""
    
    def test_enum_values(self):
        """Test that EntityType has correct string values."""
        assert EntityType.AGENT.value == "AGENT"
        assert EntityType.WORKER.value == "WORKER"
    
    def test_enum_members(self):
        """Test that all expected members exist."""
        expected_members = {"AGENT", "WORKER"}
        actual_members = {member.name for member in EntityType}
        assert actual_members == expected_members


class TestAgentType:
    """Test cases for AgentType enum."""
    
    def test_enum_values(self):
        """Test that AgentType has correct string values."""
        expected_values = {
            "PLANNER": "PlannerAgent",
            "IMPLEMENTATION": "ImplementationAgent",
            "TESTBENCH": "TestbenchAgent",
            "DEBUG": "DebugAgent",
            "INTEGRATION": "IntegrationAgent"
        }
        
        for name, expected_value in expected_values.items():
            agent_type = getattr(AgentType, name)
            assert agent_type.value == expected_value
    
    def test_enum_members(self):
        """Test that all expected members exist."""
        expected_members = {"PLANNER", "IMPLEMENTATION", "TESTBENCH", "DEBUG", "INTEGRATION"}
        actual_members = {member.name for member in AgentType}
        assert actual_members == expected_members
    
    def test_agent_type_names(self):
        """Test that agent type names are descriptive."""
        assert "Agent" in AgentType.PLANNER.value
        assert "Agent" in AgentType.IMPLEMENTATION.value
        assert "Agent" in AgentType.TESTBENCH.value
        assert "Agent" in AgentType.DEBUG.value
        assert "Agent" in AgentType.INTEGRATION.value


class TestWorkerType:
    """Test cases for WorkerType enum."""
    
    def test_enum_values(self):
        """Test that WorkerType has correct string values."""
        expected_values = {
            "LINTER": "LinterWorker",
            "SIMULATOR": "SimulatorWorker",
            "SYNTHESIZER": "SynthesizerWorker"
        }
        
        for name, expected_value in expected_values.items():
            worker_type = getattr(WorkerType, name)
            assert worker_type.value == expected_value
    
    def test_enum_members(self):
        """Test that all expected members exist."""
        expected_members = {"LINTER", "SIMULATOR", "SYNTHESIZER"}
        actual_members = {member.name for member in WorkerType}
        assert actual_members == expected_members
    
    def test_worker_type_names(self):
        """Test that worker type names are descriptive."""
        assert "Worker" in WorkerType.LINTER.value
        assert "Worker" in WorkerType.SIMULATOR.value
        assert "Worker" in WorkerType.SYNTHESIZER.value


class TestEnumIntegration:
    """Test integration between different enum types."""
    
    def test_entity_type_agent_consistency(self):
        """Test that EntityType.AGENT is consistent with AgentType values."""
        # All AgentType values should contain "Agent"
        for agent_type in AgentType:
            assert "Agent" in agent_type.value
    
    def test_entity_type_worker_consistency(self):
        """Test that EntityType.WORKER is consistent with WorkerType values."""
        # All WorkerType values should contain "Worker"
        for worker_type in WorkerType:
            assert "Worker" in worker_type.value
    
    def test_enum_imports(self):
        """Test that all enums can be imported from the main package."""
        from schemas import (
            TaskPriority,
            TaskStatus,
            EntityType,
            AgentType,
            WorkerType,
        )
        
        # Verify they are the correct types
        assert TaskPriority.LOW is not None
        assert TaskStatus.SUCCESS is not None
        assert EntityType.AGENT is not None
        assert AgentType.PLANNER is not None
        assert WorkerType.LINTER is not None
