from __future__ import annotations

import asyncio
import math
import statistics
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from guardrail.models.measurement import LatencyDistribution, RequestMetrics


class HttpWorkloadGenerator:
    """
    High-performance asynchronous HTTP workload generator.
    Accurately paces requests at a target RPS and collects microsecond-precision latency distributions.
    """

    async def generate_async(
        self,
        target_url: str,
        target_rps: float,
        duration_seconds: float,
        concurrency: int = 50,
        timeout_seconds: float = 5.0,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> RequestMetrics:
        """Execute the workload asynchronously and return aggregated metrics."""
        latencies_ms: list[float] = []
        status_codes: dict[int, int] = {}
        successful_count = 0
        failed_count = 0
        client_errors = 0
        server_errors = 0
        network_errors = 0
        timeouts = 0

        total_expected_requests = max(1, int(target_rps * duration_seconds))
        interval = 1.0 / target_rps if target_rps > 0 else 0.1
        semaphore = asyncio.Semaphore(concurrency)

        limits = httpx.Limits(
            max_keepalive_connections=concurrency, max_connections=concurrency * 2
        )
        timeout = httpx.Timeout(timeout_seconds)

        async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:

            async def send_single_request() -> None:
                nonlocal successful_count, failed_count
                nonlocal client_errors, server_errors, network_errors, timeouts
                async with semaphore:
                    t0 = time.perf_counter()
                    try:
                        resp = await client.request(
                            method=method,
                            url=target_url,
                            headers=headers or {},
                            json=payload,
                        )
                        elapsed_ms = (time.perf_counter() - t0) * 1000.0
                        latencies_ms.append(elapsed_ms)
                        code = resp.status_code
                        status_codes[code] = status_codes.get(code, 0) + 1

                        if 200 <= code < 400:
                            successful_count += 1
                        elif 400 <= code < 500:
                            failed_count += 1
                            client_errors += 1
                        else:
                            failed_count += 1
                            server_errors += 1
                    except httpx.TimeoutException:
                        elapsed_ms = (time.perf_counter() - t0) * 1000.0
                        latencies_ms.append(elapsed_ms)
                        failed_count += 1
                        timeouts += 1
                        status_codes[0] = status_codes.get(0, 0) + 1
                    except httpx.TransportError:
                        elapsed_ms = (time.perf_counter() - t0) * 1000.0
                        latencies_ms.append(elapsed_ms)
                        failed_count += 1
                        network_errors += 1
                        status_codes[0] = status_codes.get(0, 0) + 1
                    except Exception:
                        elapsed_ms = (time.perf_counter() - t0) * 1000.0
                        latencies_ms.append(elapsed_ms)
                        failed_count += 1
                        network_errors += 1
                        status_codes[0] = status_codes.get(0, 0) + 1

            tasks = []
            test_start = time.perf_counter()

            for i in range(total_expected_requests):
                # Check if duration elapsed
                now = time.perf_counter()
                if now - test_start >= duration_seconds:
                    break

                tasks.append(asyncio.create_task(send_single_request()))

                # Pace requests to match target RPS
                target_time = test_start + ((i + 1) * interval)
                delay = target_time - time.perf_counter()
                if delay > 0:
                    await asyncio.sleep(delay)

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        actual_duration = max(0.001, time.perf_counter() - test_start)
        total_reqs = successful_count + failed_count
        actual_rps = total_reqs / actual_duration
        error_rate = (server_errors + network_errors + timeouts) / total_reqs if total_reqs > 0 else 0.0
        client_error_rate = client_errors / total_reqs if total_reqs > 0 else 0.0

        # Compute percentile latencies
        distribution = self._calculate_latency_distribution(latencies_ms)

        return RequestMetrics(
            timestamp=datetime.now(UTC),
            duration_seconds=round(actual_duration, 3),
            total_requests=total_reqs,
            successful_requests=successful_count,
            failed_requests=failed_count,
            client_errors=client_errors,
            server_errors=server_errors,
            network_errors=network_errors,
            timeouts=timeouts,
            requests_per_second=round(actual_rps, 2),
            error_rate=round(error_rate, 4),
            client_error_rate=round(client_error_rate, 4),
            latency=distribution,
            status_codes=status_codes,
        )

    def generate(
        self,
        target_url: str,
        target_rps: float,
        duration_seconds: float,
        concurrency: int = 50,
        timeout_seconds: float = 5.0,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> RequestMetrics:
        """Synchronous wrapper for generate_async."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    asyncio.run,
                    self.generate_async(
                        target_url=target_url,
                        target_rps=target_rps,
                        duration_seconds=duration_seconds,
                        concurrency=concurrency,
                        timeout_seconds=timeout_seconds,
                        method=method,
                        headers=headers,
                        payload=payload,
                    ),
                )
                return future.result()
        else:
            return asyncio.run(
                self.generate_async(
                    target_url=target_url,
                    target_rps=target_rps,
                    duration_seconds=duration_seconds,
                    concurrency=concurrency,
                    timeout_seconds=timeout_seconds,
                    method=method,
                    headers=headers,
                    payload=payload,
                )
            )

    def _calculate_latency_distribution(self, latencies: list[float]) -> LatencyDistribution:
        """Calculate statistical distribution for observed latencies."""
        if not latencies:
            return LatencyDistribution(p50_ms=0.0, p95_ms=0.0, p99_ms=0.0)

        sorted_latencies = sorted(latencies)
        n = len(sorted_latencies)

        def percentile(p: float) -> float:
            k = (n - 1) * p
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                return sorted_latencies[int(k)]
            d0 = sorted_latencies[int(f)] * (c - k)
            d1 = sorted_latencies[int(c)] * (k - f)
            return d0 + d1

        p50 = percentile(0.50)
        p75 = percentile(0.75)
        p90 = percentile(0.90)
        p95 = percentile(0.95)
        p99 = percentile(0.99)
        min_v = sorted_latencies[0]
        max_v = sorted_latencies[-1]
        mean_v = statistics.mean(sorted_latencies)
        stddev_v = statistics.stdev(sorted_latencies) if n > 1 else 0.0

        return LatencyDistribution(
            p50_ms=round(p50, 2),
            p75_ms=round(p75, 2),
            p90_ms=round(p90, 2),
            p95_ms=round(p95, 2),
            p99_ms=round(p99, 2),
            min_ms=round(min_v, 2),
            max_ms=round(max_v, 2),
            mean_ms=round(mean_v, 2),
            stddev_ms=round(stddev_v, 2),
        )
