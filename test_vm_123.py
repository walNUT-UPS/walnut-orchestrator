#!/usr/bin/env python3
"""
Test script to demonstrate the enhanced Proxmox VM lifecycle dry-run system.
This directly calls the enhanced vm_lifecycle method for VM 123.
"""
import asyncio
import sys
import os

# Add the project root to the path
sys.path.insert(0, '.')

async def test_vm_123_start():
    """Test starting VM 123 using the enhanced dry-run system."""
    
    # Import the necessary modules
    from walnut.database.connection import init_database, close_database
    from walnut.transports.manager import TransportManager
    
    print("🔧 Testing Enhanced Proxmox Dry-Run System with VM 123")
    print("=" * 60)
    
    try:
        # Initialize database
        await init_database("data/walnut.db", create_tables=False)
        print("✅ Database connection established")
        
        # Mock instance configuration (based on the real integration)
        class MockInstance:
            def __init__(self):
                self.config = {
                    'host': '10.200.0.11',
                    'port': 8006,
                    'node': 'pve',
                    'token_name': 'root@pam!walnut',
                    'verify_ssl': False
                }
        
        # Mock secrets
        secrets = {'api_token': 'actual-token-from-db'}  # This would be loaded from DB in real scenario
        
        # Create transport manager
        transports = TransportManager({"host": "10.200.0.11", "port": 8006, "verify_ssl": False})
        
        # Import and create the driver
        sys.path.insert(0, './integrations/walnut.proxmox.ve')
        from driver import ProxmoxVeDriver
        
        instance = MockInstance()
        driver = ProxmoxVeDriver(instance, secrets, transports)
        
        print("✅ Proxmox driver initialized")
        print(f"   Host: {instance.config['host']}")
        print(f"   Node: {instance.config['node']}")
        print()
        
        # Create a mock target for VM 123
        class MockTarget:
            def __init__(self, external_id):
                self.external_id = external_id
        
        target_123 = MockTarget("123")
        
        print("🎯 Testing VM 123 START operation (DRY RUN)")
        print("-" * 40)
        print(f"Target VM: {target_123.external_id} (pod1-client)")
        print("Operation: START")
        print("Mode: DRY RUN (safe, no actual changes)")
        print()
        
        # Call the enhanced dry-run system
        result = await driver.vm_lifecycle("start", target_123, dry_run=True)
        
        print("📊 ENHANCED DRY-RUN RESULTS:")
        print("=" * 40)
        print(f"✅ Overall Success: {result['ok']}")
        print(f"⚠️  Severity Level: {result['severity']}")
        print(f"🔑 Idempotency Key: {result['idempotency_key']}")
        
        if result.get('reason'):
            print(f"📝 Reason: {result['reason']}")
        
        print()
        print("🔍 PRECONDITION CHECKS:")
        for i, check in enumerate(result['preconditions'], 1):
            status = "✅ PASS" if check['ok'] else "❌ FAIL"
            print(f"  {i}. {check['check']}: {status}")
            if check.get('details'):
                for key, value in check['details'].items():
                    print(f"     - {key}: {value}")
        
        print()
        print("📋 EXECUTION PLAN:")
        plan = result['plan']
        print(f"  Type: {plan['kind']}")
        print(f"  Steps: {len(plan.get('steps', []))}")
        if plan.get('steps'):
            for i, step in enumerate(plan['steps'], 1):
                print(f"    {i}. {step}")
        print(f"  Duration: ~{plan.get('estimated_duration_seconds', 0)}s")
        print(f"  Requires Confirmation: {plan.get('requires_confirmation', False)}")
        
        print()
        print("💫 EXPECTED EFFECTS:")
        effects = result['effects']
        print(f"  Summary: {effects['summary']}")
        print(f"  Business Impact: {effects.get('business_impact', 'N/A')}")
        if effects.get('per_target'):
            for target_effect in effects['per_target']:
                print(f"  Target {target_effect['id']}:")
                if target_effect.get('from'):
                    print(f"    From: {target_effect['from']}")
                if target_effect.get('to'):
                    print(f"    To: {target_effect['to']}")
        
        # Show inventory metadata if available
        if result.get('inventory_metadata'):
            print()
            print("📦 INVENTORY INTELLIGENCE:")
            inv_meta = result['inventory_metadata']
            print(f"  Strategy: {inv_meta.get('strategy_used', 'unknown')}")
            print(f"  Staleness: {inv_meta.get('staleness_seconds', 'unknown')}s")
            print(f"  Consistency: {inv_meta.get('consistency_validated', False)}")
        
        print()
        print("🎉 ENHANCED DRY-RUN SYSTEM DEMONSTRATION COMPLETE!")
        print()
        
        if result['ok'] and result['severity'] in ['info', 'warn']:
            print("✅ VM 123 (pod1-client) can be started safely")
            print("💡 The enhanced system shows this operation is:")
            print("   - Technically feasible")
            print("   - Risk-assessed and documented") 
            print("   - Ready for execution with proper safeguards")
        else:
            print("⚠️  VM 123 start operation has issues that need attention")
        
        return result
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return None
        
    finally:
        try:
            await transports.close_all()
            await close_database()
        except:
            pass

if __name__ == "__main__":
    # Set environment variables
    os.environ['WALNUT_DB_KEY'] = 'dev_dev_dev_dev_dev_dev_dev_dev_32chars'
    
    result = asyncio.run(test_vm_123_start())
    if result and result.get('ok'):
        print(f"\n🎯 SUCCESS: Enhanced dry-run system working perfectly!")
        sys.exit(0)
    else:
        print(f"\n❌ FAILED: Enhanced dry-run system needs attention")
        sys.exit(1)