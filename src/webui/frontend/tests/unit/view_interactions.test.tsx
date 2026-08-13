import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import './match_media';
import {CompareView} from '../../src/features/compare/CompareView';
import {ResultsView} from '../../src/features/results/ResultsView';
import {DatasetView} from '../../src/features/dataset/DatasetView';
import {ModelsView} from '../../src/features/models/ModelsView';
import {EvaluateView} from '../../src/features/evaluate/EvaluateView';
import {CollectView} from '../../src/features/collect/CollectView';
import {AnalyzeView} from '../../src/features/analyze/AnalyzeView';
import {RunMonitor} from '../../src/features/shared/run-monitor/RunMonitor';

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
    beginPath: vi.fn(), arc: vi.fn(), fill: vi.fn(), fillRect: vi.fn(), scale: vi.fn(), measureText: vi.fn(() => ({width: 0})),
  } as unknown as CanvasRenderingContext2D);
});

afterEach(() => cleanup());

describe('view contract coverage', () => {
  it('renders the seven tab roots', () => {
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
      expect(root?.id).toMatch(/^tab-/);
      unmount();
    });
  });
});

describe('dataset comparison stage', () => {
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
    expect(screen.getByRole('button', {name: /Second/}).getAttribute('aria-selected')).toBe('true');
  });

  it('keeps a clicked target selected, supports clear and Escape, and selects from the canvas', async () => {
    vi.stubGlobal('Image', class {
      complete = true;
      naturalWidth = 100;
      width = 100;
      height = 100;
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      set src(_value: string) { queueMicrotask(() => this.onload?.()); }
    });
    vi.mocked(fetch).mockImplementation(async (input) => {
      const path = String(input);
      if (path.endsWith('/screens')) return json({screens: ['home']});
      if (path.endsWith('/manifest')) return json({available: true, manifest: {expected_captures: 2, successful_captures: 2}});
      if (path.includes('/targets/')) return json({targets: [
        {text: 'First', baseline_box: [0, 0, 10, 10]},
        {text: 'Second', baseline_box: [20, 20, 40, 40]},
      ]});
      if (path.includes('/labels/')) return json([{text: 'First', box: [0, 0, 10, 10]}]);
      return json([]);
    });

    render(<DatasetView dataset="demo" />);
    await waitFor(() => expect(screen.getByRole('button', {name: 'First'})).toBeTruthy());
    const list = screen.getByRole('listbox');
    const first = screen.getByRole('button', {name: 'First'});
    fireEvent.click(first);
    expect(first.getAttribute('aria-selected')).toBe('true');
    expect(first.className).toContain('bg-white');
    fireEvent.click(first);
    expect(first.getAttribute('aria-selected')).toBe('true');
    fireEvent.click(screen.getByRole('button', {name: 'Clear selection'}));
    expect(first.getAttribute('aria-selected')).toBe('false');

    fireEvent.click(first);
    fireEvent.keyDown(list, {key: 'Escape'});
    expect(first.getAttribute('aria-selected')).toBe('false');
    fireEvent.keyDown(list, {key: 'ArrowDown'});
    expect(first.getAttribute('aria-selected')).toBe('true');
    fireEvent.keyDown(list, {key: 'ArrowDown'});
    expect(screen.getByRole('button', {name: /Second/}).getAttribute('aria-selected')).toBe('true');

    const canvas = document.querySelector('#canvas-baseline') as HTMLCanvasElement;
    expect(canvas).toBeTruthy();
    vi.spyOn(canvas, 'getBoundingClientRect').mockReturnValue({left: 0, top: 0, width: 100, height: 100} as DOMRect);
    fireEvent.click(canvas, {clientX: 25, clientY: 25});
    expect(screen.getByRole('button', {name: /Second/}).getAttribute('aria-selected')).toBe('true');
  });
});

describe('compare and results interactions', () => {
  it('tracks checkbox selection by stable result filename and clears all selections', async () => {
    vi.mocked(fetch).mockImplementation(async (input) => {
      if (String(input).endsWith('/results')) return json([
        {filename: 'vision-a.csv', model: 'same-model', prompt_mode: 'vision', row_count: 2, statuses: {HIT: 1}, hits: 1, co_present_count: 2, accuracy: .5, baseline_accuracy: .5},
        {filename: 'tree-b.csv', model: 'same-model', prompt_mode: 'tree', row_count: 2, statuses: {HIT: 2}, hits: 2, co_present_count: 2, accuracy: 1, baseline_accuracy: .5},
      ]);
      return json([]);
    });
    render(<ResultsView dataset="demo" />);
    await waitFor(() => expect(screen.getAllByRole('checkbox')).toHaveLength(2));
    const [first, second] = screen.getAllByRole('checkbox') as HTMLButtonElement[];
    expect(first.getAttribute('aria-checked')).toBe('false');
    expect(second.getAttribute('aria-checked')).toBe('false');

    fireEvent.click(first);
    expect(first.getAttribute('aria-checked')).toBe('true');
    expect(second.getAttribute('aria-checked')).toBe('false');
    second.focus();
    await userEvent.keyboard('[Space]');
    expect(second.getAttribute('aria-checked')).toBe('true');
    expect(screen.getByRole('button', {name: 'Clear selection'})).toBeTruthy();

    fireEvent.click(screen.getByRole('button', {name: 'Clear selection'}));
    expect(first.getAttribute('aria-checked')).toBe('false');
    expect(second.getAttribute('aria-checked')).toBe('false');
  });

  it('uses the compare query and renders significance data', async () => {
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
    expect(within(filmstrip).getByRole('button', {name: 'First'}).getAttribute('aria-current')).toBe('true');
    fireEvent.keyDown(document, {key: 'ArrowRight'});
    await waitFor(() => {
      const currentDialog = screen.getByRole('dialog', {name: 'Miss inspector'});
      const currentFilmstrip = within(currentDialog).getByLabelText('Miss filmstrip');
      expect(within(currentFilmstrip).getByRole('button', {name: 'Second'}).getAttribute('aria-current')).toBe('true');
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
