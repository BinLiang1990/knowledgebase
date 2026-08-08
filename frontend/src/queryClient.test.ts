import { describe, expect, it } from 'vitest';
import { shouldRetryQuery } from './queryClient';
import { ApiError } from './api/client';

describe('shouldRetryQuery', () => {
  it('never retries an ApiError (business/validation failures are deterministic)', () => {
    expect(shouldRetryQuery(0, new ApiError('知识库名称已存在'))).toBe(false);
  });

  it('retries a non-ApiError up to 3 times', () => {
    expect(shouldRetryQuery(0, new Error('boom'))).toBe(true);
    expect(shouldRetryQuery(2, new Error('boom'))).toBe(true);
    expect(shouldRetryQuery(3, new Error('boom'))).toBe(false);
  });
});
