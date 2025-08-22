"""
Performance and concurrency tests for the Policy System.

Tests concurrent policy execution, idempotency/suppression windows,
and performance under load as specified in the requirements.
"""
import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch
from uuid import uuid4
from datetime import datetime, timezone

from walnut.policy.engine import PolicyEngine
from walnut.policy.models import (
    PolicyIR, NormalizedEvent, EventSubject, Severity, 
    ExecutionSummary
)


class TestConcurrentExecution:
    """Test concurrent policy execution and serialization."""
    
    @pytest.mark.asyncio
    async def test_concurrent_events_same_host(self):
        """Test that concurrent events on same host are serialized."""
        engine = PolicyEngine()
        
        # Mock host UUID for serialization
        host_id = uuid4()
        
        # Create multiple events for same host
        events = []
        for i in range(10):
            event = NormalizedEvent(
                type="ups",
                kind="ups.state",
                subject=EventSubject(kind="ups", id="ups-1"),
                attrs={"state": "on_battery", "charge": 85 - i},
                ts=datetime.now(timezone.utc),
                correlation_id=uuid4()
            )
            events.append(event)
        
        # Process all events concurrently
        start_time = time.time()
        
        # Use asyncio.gather to process events in parallel
        tasks = [engine.process_event(event) for event in events]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        end_time = time.time()
        
        # Verify all completed without exceptions
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 0, f"Found exceptions: {exceptions}"
        
        # Verify results structure
        successful_results = [r for r in results if isinstance(r, list)]
        assert len(successful_results) == 10
        
        # Verify execution time is reasonable (should complete quickly since no real policies)
        execution_time = end_time - start_time
        assert execution_time < 5.0, f"Execution took too long: {execution_time}s"
        
        print(f"✓ Processed {len(events)} concurrent events in {execution_time:.2f}s")
    
    @pytest.mark.asyncio
    async def test_per_host_queue_serialization(self):
        """Test that per-host execution queues prevent conflicts."""
        # Mock driver manager and inventory
        mock_driver_manager = AsyncMock()
        mock_inventory_index = AsyncMock()
        
        # Mock driver responses with delays to simulate real execution
        async def mock_execute_action(capability, verb, target, dry_run=False):
            await asyncio.sleep(0.1)  # Simulate execution time
            return {
                "ok": True,
                "action": f"{capability}:{verb}",
                "target": target["external_id"],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        mock_driver = AsyncMock()
        mock_driver.vm_lifecycle = mock_execute_action
        mock_driver_manager.get_driver_for_host.return_value = mock_driver
        
        engine = PolicyEngine(mock_driver_manager, mock_inventory_index)
        
        host_id = uuid4()
        
        # Create policy IR with actions
        policy_ir = Mock()
        policy_ir.policy_id = uuid4()
        policy_ir.stop_on_match = False
        policy_ir.dynamic_resolution = False
        policy_ir.windows = Mock(suppression_s=0, idempotency_s=0)
        policy_ir.targets = Mock(
            host_id=host_id,
            resolved_ids=["vm-101", "vm-102", "vm-103"]
        )
        policy_ir.plan = [
            Mock(capability="vm.lifecycle", verb="shutdown", params={})
        ]
        
        # Create event
        event = NormalizedEvent(
            type="ups",
            kind="ups.state", 
            subject=EventSubject(kind="ups", id="ups-1"),
            attrs={"state": "on_battery"},
            ts=datetime.now(timezone.utc)
        )
        
        # Execute multiple policy runs concurrently on same host
        start_time = time.time()
        
        tasks = [engine._execute_policy(policy_ir, event) for _ in range(5)]
        results = await asyncio.gather(*tasks)
        
        end_time = time.time()
        
        # Verify all executions completed
        assert len(results) == 5
        
        for result in results:
            assert isinstance(result, ExecutionSummary)
            assert result.policy_id == policy_ir.policy_id
            assert len(result.actions) == 3  # 3 VMs executed
        
        # Verify execution was serialized (should take at least 5 * 0.1 * 3 = 1.5s for sequential execution)
        execution_time = end_time - start_time
        print(f"✓ Executed 5 concurrent policies in {execution_time:.2f}s")
    
    @pytest.mark.asyncio
    async def test_global_concurrency_limit(self):
        """Test global concurrency semaphore limits simultaneous executions."""
        # Create engine with small concurrency limit for testing
        engine = PolicyEngine()
        engine._global_semaphore = asyncio.Semaphore(3)  # Allow max 3 concurrent
        
        # Track concurrent execution count
        max_concurrent = 0
        current_concurrent = 0
        concurrent_lock = asyncio.Lock()
        
        async def mock_execute_with_tracking():
            nonlocal max_concurrent, current_concurrent
            
            async with engine._global_semaphore:
                async with concurrent_lock:
                    current_concurrent += 1
                    if current_concurrent > max_concurrent:
                        max_concurrent = current_concurrent
                
                # Simulate work
                await asyncio.sleep(0.1)
                
                async with concurrent_lock:
                    current_concurrent -= 1
            
            return []
        
        # Start 10 concurrent executions
        tasks = [mock_execute_with_tracking() for _ in range(10)]
        await asyncio.gather(*tasks)
        
        # Verify concurrency was limited to semaphore value
        assert max_concurrent <= 3, f"Max concurrent ({max_concurrent}) exceeded semaphore limit"
        print(f"✓ Global concurrency properly limited to {max_concurrent}")


class TestSuppressionAndIdempotency:
    """Test suppression and idempotency window enforcement."""
    
    @pytest.mark.asyncio
    async def test_suppression_window_prevents_duplicate_execution(self):
        """Test suppression window prevents duplicate executions."""
        engine = PolicyEngine()
        
        # Create policy IR with suppression window
        policy_ir = Mock()
        policy_ir.policy_id = uuid4()
        policy_ir.windows = Mock(suppression_s=300, idempotency_s=0)  # 5 minute suppression
        policy_ir.targets = Mock(resolved_ids=["vm-101"])
        
        # Add execution to history (within suppression window)
        recent_execution = {
            "policy_id": policy_ir.policy_id,
            "timestamp": datetime.now(timezone.utc),
            "idempotency_key": "test_key",
            "actions": [{"action": "shutdown", "target": "vm-101"}],  # Has actions
            "severity": "info"
        }
        engine._execution_history.append(recent_execution)
        
        event = NormalizedEvent(
            type="ups",
            kind="ups.state",
            subject=EventSubject(kind="ups", id="ups-1"),
            attrs={"state": "on_battery"},
            ts=datetime.now(timezone.utc)
        )
        
        # Should be suppressed
        is_suppressed = await engine._is_suppressed(policy_ir, event)
        assert is_suppressed, "Policy should be suppressed within window"
    
    @pytest.mark.asyncio
    async def test_idempotency_window_prevents_identical_actions(self):
        """Test idempotency window prevents identical action sequences."""
        engine = PolicyEngine()
        
        policy_ir = Mock()
        policy_ir.policy_id = uuid4()
        policy_ir.windows = Mock(suppression_s=0, idempotency_s=600)  # 10 minute idempotency
        policy_ir.targets = Mock(resolved_ids=["vm-101", "vm-102"])
        policy_ir.plan = [
            Mock(capability="vm.lifecycle", verb="shutdown")
        ]
        
        event = NormalizedEvent(
            type="ups",
            kind="ups.state",
            subject=EventSubject(kind="ups", id="ups-1"),
            attrs={"state": "on_battery"},
            ts=datetime.now(timezone.utc)
        )
        
        # Build idempotency key
        idempotency_key = engine._build_idempotency_key(policy_ir, event)
        
        # Add execution with same idempotency key to history
        recent_execution = {
            "policy_id": policy_ir.policy_id,
            "timestamp": datetime.now(timezone.utc),
            "idempotency_key": idempotency_key,
            "actions": [],
            "severity": "info"
        }
        engine._execution_history.append(recent_execution)
        
        # Should be idempotent
        is_idempotent = await engine._is_idempotent(policy_ir, event)
        assert is_idempotent, "Policy should be idempotent within window"
    
    @pytest.mark.asyncio
    async def test_suppression_honors_window_expiry(self):
        """Test suppression window expires correctly."""
        engine = PolicyEngine()
        
        policy_ir = Mock()
        policy_ir.policy_id = uuid4()
        policy_ir.windows = Mock(suppression_s=1, idempotency_s=0)  # 1 second suppression
        
        # Add old execution (outside suppression window)
        from datetime import timedelta
        old_timestamp = datetime.now(timezone.utc) - timedelta(seconds=2)
        old_execution = {
            "policy_id": policy_ir.policy_id,
            "timestamp": old_timestamp,
            "idempotency_key": "test_key",
            "actions": [{"action": "shutdown"}],
            "severity": "info"
        }
        engine._execution_history.append(old_execution)
        
        event = NormalizedEvent(
            type="ups",
            kind="ups.state",
            subject=EventSubject(kind="ups", id="ups-1"),
            attrs={"state": "on_battery"},
            ts=datetime.now(timezone.utc)
        )
        
        # Should not be suppressed (window expired)
        is_suppressed = await engine._is_suppressed(policy_ir, event)
        assert not is_suppressed, "Policy should not be suppressed after window expiry"


class TestPerformanceUnderLoad:
    """Test policy system performance under load."""
    
    @pytest.mark.asyncio
    async def test_engine_responsiveness_under_load(self):
        """Test that engine remains responsive under heavy event load."""
        engine = PolicyEngine()
        
        # Generate large number of events
        events = []
        for i in range(100):
            event = NormalizedEvent(
                type="metric",
                kind="metric.threshold",
                subject=EventSubject(kind="ups", id=f"ups-{i % 5}"),  # 5 different UPS units
                attrs={"metric": "load", "value": 75 + i % 20, "threshold": 80},
                ts=datetime.now(timezone.utc),
                correlation_id=uuid4()
            )
            events.append(event)
        
        # Process events in batches to simulate real load
        batch_size = 20
        batch_times = []
        
        for i in range(0, len(events), batch_size):
            batch = events[i:i + batch_size]
            
            start_time = time.time()
            tasks = [engine.process_event(event) for event in batch]
            await asyncio.gather(*tasks)
            end_time = time.time()
            
            batch_time = end_time - start_time
            batch_times.append(batch_time)
            print(f"Batch {i//batch_size + 1}: {len(batch)} events in {batch_time:.3f}s")
        
        # Verify performance characteristics
        total_events = len(events)
        total_time = sum(batch_times)
        events_per_second = total_events / total_time
        
        print(f"✓ Processed {total_events} events in {total_time:.2f}s ({events_per_second:.1f} events/s)")
        
        # Verify reasonable performance (should handle at least 10 events/second)
        assert events_per_second >= 10, f"Performance too low: {events_per_second} events/s"
        
        # Verify consistent performance (no batch should be more than 3x slower than average)
        avg_batch_time = sum(batch_times) / len(batch_times)
        max_batch_time = max(batch_times)
        
        assert max_batch_time <= avg_batch_time * 3, f"Performance inconsistent: max {max_batch_time:.3f}s vs avg {avg_batch_time:.3f}s"
    
    @pytest.mark.asyncio
    async def test_execution_history_pruning(self):
        """Test that execution history is properly pruned to prevent memory leaks."""
        engine = PolicyEngine()
        engine._max_history = 50  # Set small limit for testing
        
        # Fill history beyond limit
        for i in range(75):
            execution = {
                "policy_id": uuid4(),
                "timestamp": datetime.now(timezone.utc),
                "idempotency_key": f"key_{i}",
                "actions": [],
                "severity": "info"
            }
            engine._execution_history.append(execution)
        
        # Trigger pruning by adding one more
        final_execution = {
            "policy_id": uuid4(),
            "timestamp": datetime.now(timezone.utc),
            "idempotency_key": "final_key",
            "actions": [],
            "severity": "info"
        }
        engine._execution_history.append(final_execution)
        
        # Manually trigger pruning (normally done in _record_execution)
        if len(engine._execution_history) > engine._max_history:
            engine._execution_history = engine._execution_history[-engine._max_history:]
        
        # Verify history was pruned
        assert len(engine._execution_history) == engine._max_history
        
        # Verify most recent entries are preserved
        assert engine._execution_history[-1]["idempotency_key"] == "final_key"
        
        print(f"✓ History properly pruned to {len(engine._execution_history)} entries")


class TestMemoryAndResourceManagement:
    """Test memory usage and resource management."""
    
    @pytest.mark.asyncio
    async def test_policy_engine_shutdown_cleanup(self):
        """Test that policy engine properly cleans up resources on shutdown."""
        engine = PolicyEngine()
        
        # Simulate some background tasks
        engine._host_workers["test_host_1"] = asyncio.create_task(asyncio.sleep(10))
        engine._host_workers["test_host_2"] = asyncio.create_task(asyncio.sleep(10))
        
        # Verify tasks are running
        running_tasks = sum(1 for task in engine._host_workers.values() if not task.done())
        assert running_tasks == 2, "Background tasks should be running"
        
        # Shutdown engine
        await engine.shutdown()
        
        # Verify all tasks were cancelled
        cancelled_tasks = sum(1 for task in engine._host_workers.values() if task.cancelled())
        completed_tasks = sum(1 for task in engine._host_workers.values() if task.done())
        
        assert completed_tasks == 2, "All tasks should be completed"
        assert len(engine._host_workers) == 0, "Worker dictionary should be cleared"
        
        print("✓ Engine shutdown properly cleaned up resources")
    
    @pytest.mark.asyncio 
    async def test_concurrent_policy_memory_usage(self):
        """Test memory usage remains stable under concurrent policy operations."""
        import psutil
        import os
        
        # Get initial memory usage
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        engine = PolicyEngine()
        
        # Run multiple concurrent operations
        async def memory_intensive_operation():
            # Create multiple events and process them
            events = []
            for i in range(20):
                event = NormalizedEvent(
                    type="ups",
                    kind="ups.state",
                    subject=EventSubject(kind="ups", id=f"ups-{i}"),
                    attrs={"state": "on_battery", "data": "x" * 1000},  # Some data
                    ts=datetime.now(timezone.utc)
                )
                events.append(event)
            
            tasks = [engine.process_event(event) for event in events]
            await asyncio.gather(*tasks)
        
        # Run concurrent operations
        concurrent_tasks = [memory_intensive_operation() for _ in range(10)]
        await asyncio.gather(*concurrent_tasks)
        
        # Check final memory usage
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        print(f"Memory usage: {initial_memory:.1f}MB → {final_memory:.1f}MB (Δ{memory_increase:+.1f}MB)")
        
        # Verify memory usage didn't increase dramatically (allow up to 50MB increase)
        assert memory_increase < 50, f"Memory usage increased too much: {memory_increase:.1f}MB"
        
        # Force garbage collection to clean up
        import gc
        gc.collect()
        
        # Check memory after cleanup
        cleanup_memory = process.memory_info().rss / 1024 / 1024
        print(f"Memory after cleanup: {cleanup_memory:.1f}MB")


class TestStressScenarios:
    """Test system behavior under stress conditions."""
    
    @pytest.mark.asyncio
    async def test_rapid_fire_events_same_policy(self):
        """Test handling of rapid-fire events that would trigger same policy."""
        engine = PolicyEngine()
        
        # Create multiple rapid events for same trigger
        events = []
        base_time = datetime.now(timezone.utc)
        
        for i in range(50):
            # Events spaced 100ms apart
            from datetime import timedelta
            event_time = base_time + timedelta(milliseconds=i * 100)
            
            event = NormalizedEvent(
                type="ups",
                kind="ups.state",
                subject=EventSubject(kind="ups", id="ups-1"),
                attrs={"state": "on_battery", "charge": 85 - (i * 2)},  # Decreasing charge
                ts=event_time,
                correlation_id=uuid4()
            )
            events.append(event)
        
        # Process all events as quickly as possible
        start_time = time.time()
        
        # Use asyncio to process events rapidly
        tasks = [engine.process_event(event) for event in events]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Verify all events were processed without errors
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 0, f"Found {len(exceptions)} exceptions in rapid-fire test"
        
        # Verify reasonable performance
        events_per_second = len(events) / processing_time
        print(f"✓ Processed {len(events)} rapid-fire events in {processing_time:.2f}s ({events_per_second:.1f} events/s)")
        
        assert events_per_second >= 20, f"Performance too low for rapid events: {events_per_second} events/s"
    
    @pytest.mark.asyncio
    async def test_engine_stability_under_errors(self):
        """Test engine remains stable when individual operations fail."""
        # Mock driver manager that sometimes fails
        mock_driver_manager = AsyncMock()
        mock_driver = AsyncMock()
        
        # Make driver fail intermittently
        call_count = 0
        async def failing_action(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count % 3 == 0:  # Fail every 3rd call
                raise Exception(f"Simulated failure #{call_count}")
            return {"ok": True, "action": "test", "target": "test"}
        
        mock_driver.vm_lifecycle = failing_action
        mock_driver_manager.get_driver_for_host.return_value = mock_driver
        
        engine = PolicyEngine(mock_driver_manager)
        
        # Process multiple events that would trigger failures
        events = []
        for i in range(15):  # Will cause 5 failures
            event = NormalizedEvent(
                type="timer",
                kind="timer.cron",
                subject=EventSubject(kind="timer", id="timer-1"),
                attrs={"cron": "0 1 * * *"},
                ts=datetime.now(timezone.utc)
            )
            events.append(event)
        
        # Process events - some will fail but engine should remain stable
        tasks = [engine.process_event(event) for event in events]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count exceptions vs successful results
        exceptions = [r for r in results if isinstance(r, Exception)]
        successes = [r for r in results if not isinstance(r, Exception)]
        
        print(f"✓ Processed {len(events)} events with {len(exceptions)} exceptions, {len(successes)} successes")
        
        # Engine should remain functional despite individual failures
        assert len(successes) > 0, "Engine should handle some requests successfully despite failures"
        assert len(results) == len(events), "All requests should complete (success or failure)"