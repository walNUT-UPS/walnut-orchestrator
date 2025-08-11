import asyncio
import logging
from functools import wraps
from typing import Any, Callable, Coroutine, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

def async_retry(
    retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    max_delay: float = 10.0,
    jitter: float = 0.1,
    catch_exceptions: type[Exception] | tuple[type[Exception], ...] = Exception,
) -> Callable[[Callable[..., Coroutine[Any, Any, T]]], Callable[..., Coroutine[Any, Any, T]]]:
    """
    A decorator for retrying an async function with exponential backoff.

    Args:
        retries: The maximum number of retries.
        delay: The initial delay between retries in seconds.
        backoff: The multiplier for the delay for each subsequent retry.
        max_delay: The maximum delay between retries.
        jitter: A factor to add random jitter to the delay.
        catch_exceptions: The exception or tuple of exceptions to catch and retry on.
    """

    def decorator(func: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., Coroutine[Any, Any, T]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            current_delay = delay
            for attempt in range(retries + 1):
                try:
                    return await func(*args, **kwargs)
                except catch_exceptions as e:
                    if attempt == retries:
                        logger.error(
                            f"Function '{func.__name__}' failed after {retries + 1} attempts. "
                            f"Last error: {e}"
                        )
                        raise

                    logger.warning(
                        f"Attempt {attempt + 1}/{retries + 1} for '{func.__name__}' failed. "
                        f"Retrying in {current_delay:.2f}s. Error: {e}"
                    )

                    # Add jitter to the delay
                    jitter_amount = current_delay * jitter * (2 * asyncio.get_event_loop().time() % 1 - 1)
                    await asyncio.sleep(current_delay + jitter_amount)

                    current_delay = min(current_delay * backoff, max_delay)

            # This line should not be reachable, but mypy complains without it
            raise RuntimeError("Retry loop exited unexpectedly")

        return wrapper

    return decorator
