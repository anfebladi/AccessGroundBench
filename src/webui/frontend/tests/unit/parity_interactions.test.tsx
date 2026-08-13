import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {CompareView, ResultsView} from '../../src/reporting/views';
import {DatasetView} from '../../src/views/DatasetView';
import {ModelsView} from '../../src/views/ModelsView';
import {EvaluateView} from '../../src/views/EvaluateView';
import {CollectView} from '../../src/views/CollectView';
import {AnalyzeView} from '../../src/reporting/views';
import {RunMonitor} from '../../src/views/RunMonitor';

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), {
  status,
  headers: {'Content-Type': 'application/json'},
});

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
  vi.stubGlobal('fetch', vi.fn(async () => json([])));
  vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
    drawImage: vi.fn(), clearRect: vi.fn(), fillText: vi.fn(), strokeRect: vi.fn(),
    beginPath: vi.fn(), arc: vi.fn(), fill: vi.fn(), scale: vi.fn(),
  } as unknown as CanvasRenderingContext2D);
});

afterEach(() => cleanup());

describe('legacy view contract coverage', () => {
  it('renders the seven historical tab roots', () => {
    const views = [
      <DatasetView dataset="demo" />,
      <ModelsView />,
      <EvaluateView dataset="demo" models={[]} />,
      <CollectView />,
      <CompareView dataset="demo" />,
      <ResultsView dataset="demo" />,
      <AnalyzeView dataset="demo" />,
    ];

    views.forEach((view) => {
      const {unmount} = render(view);
      const root = document.querySelector('[id^="tab-"]');
      expect(root).not.toBeNull();
      expect(root?.classList.contains('tab')).toBe(true);
      unmount();
    });
  });
});

describe('dataset comparison stage parity', () => {
  it('loads comparison data and advances the target with keyboard navigation', async () => {
    vi.mocked(fetch).mockImplementation(async (input) => {
      const path = String(input);
      if (path.endsWith('/screens')) return json({screens: ['home']});
      if (path.endsWith('/manifest')) return json({available: true, manifest: {expected_captures: 2, successful_captures: 2}});
      if (path.includes('/targets/')) return json({targets: [
        {text: 'First', baseline_box: [0, 0, 10, 10]},
        {text: 'Second', baseline_box: [10, 10, 20, 20]},
      ]});
      if (path.includes('/labels/')) return json([{text: 'First', box: [0, 0, 10, 10]}]);
      return json([]);
    });

    render(<DatasetView dataset="demo" />);
    await waitFor(() => expect(screen.getByRole('button', {name: 'First'})).toBeTruthy());
    const list = screen.getByRole('listbox');
    fireEvent.click(screen.getByRole('button', {name: 'First'}));
    fireEvent.keyDown(list, {key: 'ArrowDown'});
    expect(screen.getByRole('button', {name: /Second/}).className).toContain('is-selected');
  });
});

describe('compare and results interaction parity', () => {
  it('uses the historical compare query and renders significance data', async () => {
    const calls: string[] = [];
    vi.mocked(fetch).mockImplementation(async (input) => {
      const path = String(input);
      calls.push(path);
      if (path.endsWith('/results')) return json([{filename: 'r.csv', model: 'model-a', prompt_mode: 'vision', row_count: 2, statuses: {HIT: 2}, hits: 2, co_present_count: 2, accuracy: 1, baseline_accuracy: .5}]);
      if (path.includes('/results/compare?')) return json({model: 'model-a', mode: 'vision', models_in_family: ['model-a'], profiles: [{profile: 'high_contrast', baseline_accuracy: 50, profile_accuracy: 25, delta: 25, b: 1, c: 0, reachability: .8, significance_state: 'significant'}]});
      return json([]);
    });
    render(<CompareView dataset="demo" />);
    await waitFor(() => expect(screen.getByText('Baseline versus each profile')).toBeTruthy());
    expect(calls.some((path) => path === '/api/datasets/demo/results/compare?model=model-a&mode=vision&sample=primary')).toBe(true);
    expect(screen.getByText('significant')).toBeTruthy();
  });

  it('supports miss inspector filmstrip navigation and Escape close', async () => {
    vi.mocked(fetch).mockImplementation(async (input) => {
      const path = String(input);
      if (path.endsWith('/results')) return json([{filename: 'r.csv', model: 'model-a', prompt_mode: 'vision', row_count: 2, statuses: {MISS: 2}, hits: 0, co_present_count: 2, accuracy: 0, baseline_accuracy: .5}]);
      if (path.includes('/rows')) return json([
        {status: 'co_present', score: '0', target_text: 'First', screen: 'home', profile: 'baseline'},
        {status: 'co_present', score: '0', target_text: 'Second', screen: 'settings', profile: 'baseline'},
      ]);
      return json([]);
    });
    render(<ResultsView dataset="demo" />);
    await waitFor(() => fireEvent.click(screen.getByRole('button', {name: /Misses/})));
    await waitFor(() => expect(screen.getByRole('dialog', {name: 'Miss inspector'})).toBeTruthy());
    const dialog = screen.getByRole('dialog', {name: 'Miss inspector'});
    const filmstrip = within(dialog).getByLabelText('Miss filmstrip');
    expect(within(filmstrip).getByRole('button', {name: 'First'}).classList.contains('selected')).toBe(true);
    fireEvent.keyDown(document, {key: 'ArrowRight'});
    await waitFor(() => {
      const currentDialog = screen.getByRole('dialog', {name: 'Miss inspector'});
      const currentFilmstrip = within(currentDialog).getByLabelText('Miss filmstrip');
      expect(within(currentFilmstrip).getByRole('button', {name: 'Second'}).classList.contains('selected')).toBe(true);
    });
    fireEvent.keyDown(document, {key: 'Escape'});
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });
});

describe('run cancellation contract', () => {
  it('posts cancellation to the exact run endpoint', async () => {
    const calls: Array<{path: string; method?: string}> = [];
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      calls.push({path: String(input), method: init?.method});
      if (String(input).includes('/runs/run-1?')) return json({status: 'running', lines: [], next_since: 0});
      if (String(input).endsWith('/cancel')) return json({ok: true});
      return json([]);
    });
    render(<RunMonitor runId="run-1" expectedTotal={2} />);
    await waitFor(() => expect((screen.getByRole('button', {name: 'Cancel run'}) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button', {name: 'Cancel run'}));
    await waitFor(() => expect(calls).toContainEqual({path: '/api/runs/run-1/cancel', method: 'POST'}));
  });
});
