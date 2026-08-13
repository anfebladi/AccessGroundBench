import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
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
  const {App} = await import('./main');
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

  it('routes command-palette selection to a view and keeps route visibility exclusive', async () => {
    await renderApp();
    fireEvent.click(screen.getByRole('button', {name: 'Open command palette'}));
    const palette = screen.getByRole('dialog', {name: 'Command palette'});
    const input = within(palette).getByRole('combobox');
    fireEvent.change(input, {target: {value: 'Analyze'}});
    fireEvent.keyDown(input, {key: 'Enter'});
    await waitFor(() => expect(window.location.hash).toBe('#analyze'));
    await waitFor(() => assertVisibleRoute('analyze'));
    expect(document.getElementById('palette-backdrop')?.hasAttribute('hidden')).toBe(true);
  });

  it('routes numeric shortcuts to each view without unmounting the sections', async () => {
    await renderApp();
    for (const [index, tab] of tabs.entries()) {
      fireEvent.keyDown(document, {key: String(index + 1)});
      await waitFor(() => expect(window.location.hash).toBe(`#${tab}`));
      await waitFor(() => assertVisibleRoute(tab));
    }
  });
});
