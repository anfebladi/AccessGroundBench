import {afterAll, beforeAll, describe, expect, it, vi} from 'vitest';

// main.tsx mounts the browser app as a module side effect; keep these unit tests
// focused on its exported route/API helpers and avoid a React scheduler task
// surviving jsdom teardown.
vi.mock('react-dom/client', () => ({createRoot: () => ({render: vi.fn(), unmount: vi.fn()})}));

let api: typeof import('./main').api;
let normalizeTab: typeof import('./main').normalizeTab;
let isTerminalRunStatus: typeof import('./main').isTerminalRunStatus;

beforeAll(async () => {
  document.body.innerHTML = '<div id="root"></div>';
  Object.defineProperty(window, 'scrollTo', {configurable: true, value: vi.fn()});
  ({api, normalizeTab, isTerminalRunStatus} = await import('./main'));
});

afterAll(() => {
  document.getElementById('root')?.replaceChildren();
});

describe('workflow route selection', () => {
  it.each([
    ['dataset', 'dataset'],
    ['models', 'models'],
    ['evaluate', 'evaluate'],
    ['collect', 'collect'],
    ['compare', 'compare'],
    ['results', 'results'],
    ['analyze', 'analyze'],
  ])('keeps the supported hash route %s', (route, expected) => {
    expect(normalizeTab(route)).toBe(expected);
  });

  it.each(['', 'unknown', 'Dataset', 'results?file=x'])('falls back for invalid route %s', route => {
    expect(normalizeTab(route)).toBe('dataset');
  });
});

describe('run polling terminal state', () => {
  it.each(['completed', 'failed', 'cancelled'])('stops polling for %s', status => {
    expect(isTerminalRunStatus(status)).toBe(true);
  });

  it.each(['queued', 'running', 'starting', ''])('continues polling for %s', status => {
    expect(isTerminalRunStatus(status)).toBe(false);
  });
});

describe('typed API boundary', () => {
  it('returns decoded JSON for successful responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ok: true}), {status: 200, headers: {'Content-Type': 'application/json'}}),
    ));
    await expect(api<{ok: boolean}>('/api/health')).resolves.toEqual({ok: true});
  });

  it('surfaces the server detail for failed responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({detail: 'dataset not found'}), {status: 404}),
    ));
    await expect(api('/api/missing')).rejects.toThrow('dataset not found');
  });

  it('uses a stable status fallback when the error body is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('oops', {status: 503})));
    await expect(api('/api/down')).rejects.toThrow('Request failed (503)');
  });
});
