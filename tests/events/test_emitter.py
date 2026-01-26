"""Tests for EventEmitter."""

from unittest.mock import AsyncMock, patch

import pytest

from orchestrator.events.emitter import EventEmitter, create_event_emitter
from orchestrator.events.types import EventPriority, EventType, WorkflowEvent


class TestEventEmitter:
    """Tests for EventEmitter class."""

    def test_create_event_emitter(self):
        """Test factory function."""
        emitter = create_event_emitter("test-project")
        assert emitter.project_name == "test-project"
        assert emitter.enabled is True
        assert emitter.batch_size == 10

    def test_create_event_emitter_disabled(self):
        """Test creating disabled emitter."""
        emitter = create_event_emitter("test-project", enabled=False)
        assert emitter.enabled is False

    @pytest.mark.asyncio
    async def test_emit_adds_to_batch(self):
        """Test that emit adds events to batch."""
        emitter = EventEmitter("test-project", batch_size=10)
        emitter.enabled = True

        # Mock the DB write
        with patch.object(emitter, "_write_event", new_callable=AsyncMock) as mock_write:
            event = WorkflowEvent(
                event_type=EventType.NODE_START,
                project_name="test-project",
            )

            await emitter.emit(event)

            # Should be in batch, not written yet (batch not full)
            assert len(emitter._batch) == 1
            mock_write.assert_not_called()

    @pytest.mark.asyncio
    async def test_emit_when_disabled_does_nothing(self):
        """Test that emit does nothing when disabled."""
        emitter = EventEmitter("test-project", enabled=False)

        event = WorkflowEvent(
            event_type=EventType.NODE_START,
            project_name="test-project",
        )

        await emitter.emit(event)

        assert len(emitter._batch) == 0

    @pytest.mark.asyncio
    async def test_emit_filters_by_priority(self):
        """Test that low priority events are filtered when min_priority is higher."""
        emitter = EventEmitter(
            "test-project",
            min_priority=EventPriority.HIGH,
        )

        # Low priority event should be filtered
        low_event = WorkflowEvent(
            event_type=EventType.NODE_START,
            project_name="test-project",
            priority=EventPriority.LOW,
        )
        await emitter.emit(low_event)
        assert len(emitter._batch) == 0

        # High priority should pass
        high_event = WorkflowEvent(
            event_type=EventType.ERROR_OCCURRED,
            project_name="test-project",
            priority=EventPriority.HIGH,
        )
        await emitter.emit(high_event)
        assert len(emitter._batch) == 1

    @pytest.mark.asyncio
    async def test_emit_now_writes_immediately(self):
        """Test that emit_now writes without batching."""
        emitter = EventEmitter("test-project")

        with patch.object(emitter, "_write_event", new_callable=AsyncMock) as mock_write:
            event = WorkflowEvent(
                event_type=EventType.ERROR_OCCURRED,
                project_name="test-project",
            )

            await emitter.emit_now(event)

            # Should be written immediately
            mock_write.assert_called_once_with(event)
            assert len(emitter._batch) == 0

    @pytest.mark.asyncio
    async def test_batch_flushes_when_full(self):
        """Test that batch is flushed when full."""
        emitter = EventEmitter("test-project", batch_size=3)

        with patch.object(emitter, "_flush_batch", new_callable=AsyncMock) as mock_flush:
            for i in range(3):
                event = WorkflowEvent(
                    event_type=EventType.NODE_START,
                    project_name="test-project",
                )
                await emitter.emit(event)

            # Should have flushed after 3 events
            mock_flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_flush_writes_all_pending(self):
        """Test that flush writes all pending events."""
        emitter = EventEmitter("test-project", batch_size=10)

        with patch.object(emitter, "_write_event", new_callable=AsyncMock) as mock_write:
            # Add some events
            for i in range(5):
                event = WorkflowEvent(
                    event_type=EventType.NODE_START,
                    project_name="test-project",
                )
                emitter._batch.append(event)

            await emitter.flush()

            # Should have written all 5 events
            assert mock_write.call_count == 5
            assert len(emitter._batch) == 0

    @pytest.mark.asyncio
    async def test_close_flushes_remaining(self):
        """Test that close flushes remaining events."""
        emitter = EventEmitter("test-project")

        with patch.object(emitter, "flush", new_callable=AsyncMock) as mock_flush:
            emitter._batch.append(
                WorkflowEvent(event_type=EventType.NODE_START, project_name="test")
            )

            await emitter.close()

            mock_flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_callback_is_called(self):
        """Test that callbacks are called on emit."""
        emitter = EventEmitter("test-project")

        callback_called = []

        def callback(event):
            callback_called.append(event)

        emitter.add_callback(callback)

        event = WorkflowEvent(
            event_type=EventType.NODE_START,
            project_name="test-project",
        )
        await emitter.emit(event)

        assert len(callback_called) == 1
        assert callback_called[0] == event

    @pytest.mark.asyncio
    async def test_remove_callback(self):
        """Test removing a callback."""
        emitter = EventEmitter("test-project")

        callback_called = []

        def callback(event):
            callback_called.append(event)

        emitter.add_callback(callback)
        emitter.remove_callback(callback)

        event = WorkflowEvent(
            event_type=EventType.NODE_START,
            project_name="test-project",
        )
        await emitter.emit(event)

        assert len(callback_called) == 0

    def test_stats(self):
        """Test stats property."""
        emitter = EventEmitter("test-project")
        emitter._events_emitted = 10
        emitter._events_failed = 2
        emitter._batch = [None, None, None]

        stats = emitter.stats

        assert stats["events_emitted"] == 10
        assert stats["events_failed"] == 2
        assert stats["events_pending"] == 3


class TestEventTypes:
    """Tests for event type definitions."""

    def test_workflow_event_to_dict(self):
        """Test WorkflowEvent.to_dict()."""
        event = WorkflowEvent(
            event_type=EventType.NODE_START,
            project_name="test-project",
            node_name="planning",
            phase=1,
            data={"key": "value"},
        )

        d = event.to_dict()

        assert d["event_type"] == "node_start"
        assert d["project_name"] == "test-project"
        assert d["node_name"] == "planning"
        assert d["phase"] == 1
        assert d["data"] == {"key": "value"}

    def test_workflow_event_from_dict(self):
        """Test WorkflowEvent.from_dict()."""
        d = {
            "event_type": "node_end",
            "project_name": "test-project",
            "node_name": "planning",
            "phase": 1,
            "priority": "high",
            "data": {"success": True},
        }

        event = WorkflowEvent.from_dict(d)

        assert event.event_type == EventType.NODE_END
        assert event.project_name == "test-project"
        assert event.node_name == "planning"
        assert event.phase == 1
        assert event.priority == EventPriority.HIGH
        assert event.data == {"success": True}
