"""One explicit retry through the caller's existing shared model budget."""

import asyncio
import logging

from deeptrace.domain import ErrorCategory
from deeptrace.harness.model_gateway import ModelCallError


async def invoke_readonly_with_recovery(gateway, *, role, messages):
    try:
        return await gateway.invoke(role=role, messages=messages)
    except ModelCallError as exc:
        if exc.category != ErrorCategory.TRANSIENT:
            raise
    logging.getLogger(__name__).info('Retrying transient %s call through shared budget', role)
    await asyncio.sleep(0.2)
    # Call the outer gateway again: admission, ledger and usage count this as
    # another dispatch. Never retry inside an already admitted provider call.
    return await gateway.invoke(role=role, messages=messages)
