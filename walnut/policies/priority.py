from typing import List, Dict, Any

def recompute_priorities(ordered_policies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Recomputes policy priorities based on a new order.
    The top of the list (order 0) gets the highest priority (255).
    """
    if not ordered_policies:
        return []

    # Sort policies by the 'order' field
    sorted_policies = sorted(ordered_policies, key=lambda p: p.get("order", 0))

    num_policies = len(sorted_policies)

    # Simple linear mapping from order to priority
    # For a small number of policies, this is fine.
    # For a large number, the priorities might be very close.
    # A different distribution could be used if needed.

    result = []
    for i, policy in enumerate(sorted_policies):
        # Top of the list (i=0) should have highest priority (255)
        priority = 255 - i
        if priority < 0:
            priority = 0

        result.append({"id": policy["id"], "priority": priority})

    return result
