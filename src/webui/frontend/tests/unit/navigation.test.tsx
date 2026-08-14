import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

vi.mock('react-dom/client', () => ({createRoot: () => ({render: vi.fn(), unmount: vi.fn()})}));

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), {
  status,
  headers: {'Content-Type': 'application/json'},
});

const tabs = ['dataset', 'models', 'evaluate', 'collect', 'compare', 'results', 'analyze'] as const;

function mockFixtureApi() {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    if (path === '/api/datasets') return json([{name: 'demo', screen_count: 2, image_count: 4, is_archived: false}]);
    if (path === '/api/providers') return json([]);
    if (path.endsWith('/screens')) return json({screens: ['home', 'settings']});
    if (path.endsWith('/manifest')) return json({available: true, manifest: {expected_captures: 2, successful_captures: 2, problems: []}});
    if (path.includes('/targets/')) return json({targets: []});
    if (path.includes('/labels/')) return json([]);
    if (path.includes('/preflight')) return json({expected_total: 0, already_done: 0, results_csv: 'results.csv', lock_present: false});
    if (path === '/api/collect/screens') return json({all_screens: ['home', 'settings']});
    if (path.includes('/results')) return json([]);
    if (path.includes('/analysis')) return json({available: false, reachability: [], pooled_permutation: [], mcnemar_per_model: [], direction_consistency: []});
    return json([]);
  }));
}

function installCanvasAndImageStubs() {
  vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
  vi.stubGlobal('Image', class {
    width = 800;
    height = 600;
    naturalWidth = 800;
    complete = true;
    onload?: () => void;
    onerror?: () => void;
    set src(_value: string) { queueMicrotask(() => this.onload?.()); }
  });
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
    drawImage: vi.fn(), clearRect: vi.fn(), fillText: vi.fn(), strokeRect: vi.fn(),
    beginPath: vi.fn(), arc: vi.fn(), fill: vi.fn(), scale: vi.fn(),
  } as unknown as CanvasRenderingContext2D);
}

async function renderApp() {
  window.location.hash = '#dataset';
  mockFixtureApi();
  installCanvasAndImageStubs();
  const {App} = await import('../../src/main');
  render(<App />);
  await waitFor(() => expect(screen.getByDisplayValue('demo')).toBeTruthy());
}

function assertVisibleRoute(selected: typeof tabs[number]) {
  for (const tab of tabs) {
    const section = document.getElementById(`tab-${tab}`);
    expect(section, `missing #tab-${tab}`).not.toBeNull();
    expect(section?.hidden, `${tab} visibility`).toBe(tab !== selected);
  }
  const selectedLink = document.querySelector(`a[data-tab="${selected}"]`);
  expect(selectedLink).not.toBeNull();
  expect(selectedLink?.getAttribute('aria-current')).toBe('page');
  for (const tab of tabs.filter((tab) => tab !== selected)) {
    expect(document.querySelector(`a[data-tab="${tab}"]`)?.getAttribute('aria-current')).toBeNull();
  }
}

describe('App section navigation', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => cleanup());

  it('switches sections through every rail link and hides the other mounted views', async () => {
    await renderApp();
    assertVisibleRoute('dataset');

    for (const tab of tabs) {
      fireEvent.click(document.querySelector(`a[data-tab="${tab}"]`) as HTMLAnchorElement);
      await waitFor(() => expect(window.location.hash).toBe(`#${tab}`));
      await waitFor(() => assertVisibleRoute(tab));
    }
  });

  it('routes numeric shortcuts to each view without unmounting the sections', async () => {
    await renderApp();
    for (const [index, tab] of tabs.entries()) {
      fireEvent.keyDown(document, {key: String(index + 1)});
      await waitFor(() => expect(window.location.hash).toBe(`#${tab}`));
      await waitFor(() => assertVisibleRoute(tab));
    }
  });

  it('propagates provider credential changes to the sidebar chip', async () => {
    localStorage.setItem('agb_models', JSON.stringify([{id: 'openai/test', coord_space: 'pixel'}]));
    let configured = false;
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === '/api/datasets') return json([{name: 'demo', screen_count: 1, image_count: 1, is_archived: false}]);
      if (path === '/api/providers') return json([{provider: 'openai', env_vars: ['OPENAI_API_KEY'], configured, session_configured: configured}]);
      if (path === '/api/keys' && init?.method === 'POST') {
        configured = true;
        return json({ok: true});
      }
      if (path.endsWith('/screens')) return json({screens: ['home']});
      if (path.includes('/results')) return json([]);
      return json([]);
    }));
    window.location.hash = '#models';
    installCanvasAndImageStubs();
    const {App} = await import('../../src/main');
    render(<App />);
    await waitFor(() => expect(screen.getByPlaceholderText('Paste key for this session')).toBeTruthy());
    expect(screen.getByRole('link', {name: /Models/}).textContent).toContain('0 providers');

    fireEvent.change(screen.getByPlaceholderText('Paste key for this session'), {target: {value: 'secret'}});
    fireEvent.click(screen.getByRole('button', {name: 'Set'}));
    await waitFor(() => expect(screen.getByRole('link', {name: /Models/}).textContent).toContain('1 provider'));
  });

  it('projects the evaluate preflight summary into the mounted sidebar chip', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path === '/api/datasets') {
        return json([{name: 'demo', screen_count: 1, image_count: 1, is_archived: false}]);
      }
      if (path === '/api/providers') return json([]);
      if (path.endsWith('/screens')) return json({screens: ['home']});
      if (path.includes('/preflight')) {
        return json({
          expected_total: 4,
          already_done: 1,
          results_csv: 'results.csv',
          lock_present: false,
        });
      }
      return json([]);
    }));
    localStorage.setItem('agb_models', JSON.stringify([{id: 'openai/test', coord_space: 'pixel'}]));
    window.location.hash = '#evaluate';
    installCanvasAndImageStubs();
    const {App} = await import('../../src/main');

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('link', {name: /Evaluate/}).textContent).toContain('3 queries left');
    });
    expect(document.getElementById('tab-evaluate')?.hidden).toBe(false);
    expect(document.getElementById('tab-models')?.hidden).toBe(true);
  });
});
