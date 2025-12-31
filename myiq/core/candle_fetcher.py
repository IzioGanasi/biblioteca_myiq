import asyncio
from myiq.models.base import Candle

async def fetch_all_candles(iq, active_id: int, duration: int, total_count: int) -> list[Candle]:
    """Fetch an arbitrary number of candles, handling the 1000‑candle API limit.

    Parameters
    ----------
    iq: IQOption
        An already‑connected client instance.
    active_id: int
        Instrument identifier.
    duration: int
        Candle duration in seconds.
    total_count: int
        Desired total number of candles (may be > 1000).
    """
    collected: list[Candle] = []
    while len(collected) < total_count:
        remaining = total_count - len(collected)
        batch = await iq.get_candles(active_id, duration, min(1000, remaining))
        if not batch:
            break
        collected.extend(batch)
        # small pause to avoid hitting rate limits
        await asyncio.sleep(0.2)
    return collected[:total_count]
