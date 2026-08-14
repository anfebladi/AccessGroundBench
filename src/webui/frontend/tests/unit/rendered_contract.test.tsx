import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import contract from '../../ui-contract.json';

vi.mock('react-dom/client', () => ({createRoot: () => ({render: vi.fn(), unmount: vi.fn()})}));

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), {
  status,
  headers: {'Content-Type': 'application/json'},
});

beforeEach(() => {
  window.location.hash = '#dataset';
  localStorage.clear();
  vi.restoreAllMocks();
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    if (path === '/api/datasets') return json([{name: 'demo', screen_count: 2, image_count: 4, is_archived: false}]);
    if (path === '/api/providers') return json([{provider: 'openai', env_vars: ['OPENAI_API_KEY'], configured: true, env_configured: true}]);
    if (path.endsWith('/screens')) return json({screens: ['home', 'settings']});
    if (path.endsWith('/manifest')) return json({available: true, manifest: {expected_captures: 2, successful_captures: 2, problems: []}});
    if (path.includes('/targets/')) return json({targets: [{text: 'Save', baseline_box: [1, 2, 20, 30]}]});
    if (path.includes('/labels/')) return json([{text: 'Save', box: [1, 2, 20, 30]}]);
    if (path.includes('/preflight')) return json({expected_total: 2, already_done: 0, results_csv: 'results.csv', lock_present: false});
    if (path === '/api/collect/screens') return json({all_screens: ['home', 'settings']});
    if (path.includes('/results')) return json([]);
    if (path.includes('/analysis')) return json({available: false, reachability: [], pooled_permutation: [], mcnemar_per_model: [], direction_consistency: []});
    return json([]);
  }));
  vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
    drawImage: vi.fn(), clearRect: vi.fn(), fillText: vi.fn(), strokeRect: vi.fn(),
    beginPath: vi.fn(), arc: vi.fn(), fill: vi.fn(), scale: vi.fn(),
  } as unknown as CanvasRenderingContext2D);
  vi.stubGlobal('Image', class {
    width = 800; height = 600; naturalWidth = 800; complete = true;
    onload?: () => void; onerror?: () => void;
    set src(_value: string) { queueMicrotask(() => this.onload?.()); }
  });
});

afterEach(() => cleanup());

describe('rendered legacy contract', () => {
  it('contains every required historical ID, data hook, and control in the React DOM', async () => {
    const {App} = await import('../../src/main');
    render(<App />);
    await waitFor(() => expect(screen.getByText('demo')).toBeTruthy());

    for (const id of contract.dom_ids) expect(document.getElementById(id), `missing #${id}`).not.toBeNull();
    for (const selector of contract.data_hooks) expect(document.querySelector(`[${selector}]`), `missing [${selector}]`).not.toBeNull();
    for (const selector of contract.controls) {
      if (selector === 'button[submit]') expect(document.querySelectorAll('button[type="submit"]').length).toBeGreaterThan(0);
      else if (selector.startsWith('a[#')) {
        const href = selector.slice(2, -1);
        expect(document.querySelector(`a[href="${href}"]`), `missing ${selector}`).not.toBeNull();
      } else expect(document.querySelector(selector), `missing ${selector}`).not.toBeNull();
    }
    expect(document.querySelectorAll('[role="navigation"], nav').length).toBeGreaterThan(0);
    expect(document.querySelectorAll('main [aria-labelledby]').length).toBeGreaterThanOrEqual(7);
  });

  it('keeps rail chips wired to the shell', async () => {
    const {App} = await import('../../src/main');
    render(<App />);
    await waitFor(() => expect(screen.getByText('demo')).toBeTruthy());
    expect(screen.getByText('2 screens')).toBeTruthy();
    expect(screen.getByText('none configured')).toBeTruthy();
  });

  it('does not let contenteditable fields trigger global numeric shortcuts', async () => {
    const {App} = await import('../../src/main');
    render(<App />);
    await waitFor(() => expect(screen.getByText('demo')).toBeTruthy());
    const editable = document.createElement('div');
    editable.contentEditable = 'true';
    document.body.appendChild(editable);
    editable.focus();
    fireEvent.keyDown(editable, {key: '2'});
    expect(window.location.hash).toBe('#dataset');
    editable.remove();
  });
});
