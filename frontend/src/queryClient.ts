import { QueryClient } from '@tanstack/react-query';
import { ApiError } from './api/client';

// A 444/422 business or validation error is deterministic — retrying it
// wastes round-trips and delays the failure UI for no benefit. Only retry
// (up to the default 3 times) for genuine transient failures. Exported
// standalone so it's unit-testable without spinning up real retries.
// Found by the Kimi review gate on PR #22.
export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  return !(error instanceof ApiError) && failureCount < 3;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: shouldRetryQuery },
    },
  });
}
