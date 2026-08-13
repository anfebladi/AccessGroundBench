import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import './match_media';
import {DatasetView} from '../../src/features/dataset/DatasetView';
import {ModelsView} from '../../src/features/models/ModelsView';
import {EvaluateView} from '../../src/features/evaluate/EvaluateView';
import {CollectView} from '../../src/features/collect/CollectView';
import {RunMonitor} from '../../src/features/shared/run-monitor/RunMonitor';
import {AnalyzeView} from '../../src/features/analyze/AnalyzeView';
import {ResultsView} from '../../src/features/results/ResultsView';
import {CaptureHealth} from '../../src/features/dataset/CaptureHealth';

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), {
  status,
  headers: {'Content-Type': 'application/json'},
});

const datasets = [{name: 'demo', screen_count: 2, image_count: 4, is_archived: false}];

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
  vi.stubGlobal('fetch', vi.fn(async () => json([])));
  vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
  vi.stubGlobal('Image', class {
    width = 800; height = 600; naturalWidth = 800; complete = true;
    onload?: () => void; onerror?: () => void;
    set src(_value: string) { queueMicrotask(() => this.onload?.()); }
  });
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
    drawImage: vi.fn(), clearRect: vi.fn(), fillText: vi.fn(), strokeRect: vi.fn(),
    beginPath: vi.fn(), arc: vi.fn(), fill: vi.fn(), scale: vi.fn(),
  } as unknown as CanvasRenderingContext2D);
  vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation((cb) => cb(new Blob(['png'], {type: 'image/png'})));
  Object.defineProperty(URL, 'createObjectURL', {configurable: true, value: vi.fn().mockReturnValue('blob:test')});
  Object.defineProperty(URL, 'revokeObjectURL', {configurable: true, value: vi.fn()});
  Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {writeText: vi.fn().mockResolvedValue(undefined)}});
});

afterEach(() => cleanup());

describe('DatasetView', () => {
  it('loads screens, filters them, and changes the selected screen', async () => {
    vi.mocked(fetch).mockImplementation(async (input) => {
      const path = String(input);
      if (path.endsWith('/screens')) return json({screens: ['home', 'settings', 'help']});
      if (path.endsWith('/manifest')) return json({available: true, manifest: {expected_captures: 3, successful_captures: 3}});
      if (path.includes('/targets/')) return json({targets: []});
      return json([]);
    });
    render(<DatasetView dataset="demo" />);
    await waitFor(() => expect(screen.getByText('home')).toBeTruthy());
    fireEvent.change(screen.getByRole('searchbox', {name: 'Filter screens'}), {target: {value: 'set'}});
    expect(screen.getByText('settings')).toBeTruthy();
    expect(screen.queryByText('home')).toBeNull();
    fireEvent.click(screen.getByRole('button', {name: 'settings'}));
    const selectedItem = screen.getByRole('button', {name: 'settings'}).closest('li');
    expect(selectedItem?.getAttribute('data-screen')).toBe('settings');
    expect(selectedItem?.className).toContain('bg-[var(--primary)]');
  });

  it('keeps screen picker parity and places capture health before screen comparison', async () => {
    vi.mocked(fetch).mockImplementation(async (input) => {
      const path = String(input);
      if (path.endsWith('/screens')) return json({screens: ['home', 'settings']});
      if (path.endsWith('/manifest')) {
        return json({
          available: true,
          manifest: {
            expected_captures: 2,
            successful_captures: 1,
            problems: ['settings capture is incomplete'],
          },
        });
      }
      if (path.includes('/targets/')) return json({targets: []});
      if (path.includes('/labels/')) return json([]);
      return json([]);
    });

    render(<DatasetView dataset="demo" />);
    await waitFor(() => expect(screen.getByRole('button', {name: 'home'})).toBeTruthy());

    const pickerButtons = screen.getAllByRole('button').filter((button) =>
      button.closest('li[data-screen]'),
    );
    expect(pickerButtons).toHaveLength(2);

    fireEvent.click(screen.getByRole('button', {name: 'settings'}));
    const settingsItem = screen.getByRole('button', {name: 'settings'}).closest('li');
    const homeItem = screen.getByRole('button', {name: 'home'}).closest('li');
    expect(settingsItem?.getAttribute('data-screen')).toBe('settings');
    expect(settingsItem?.className).toContain('bg-[var(--primary)]');
    expect(homeItem?.className).not.toContain('bg-[var(--primary)]');

    expect(screen.getByText('settings capture is incomplete')).toBeTruthy();
    const captureHealth = screen.getByRole('heading', {name: 'Capture health'});
    const comparison = screen.getByRole('heading', {name: 'Screen comparison'});
    expect(captureHealth.compareDocumentPosition(comparison) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('renders datasets containing non-text labels without crashing', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    vi.mocked(fetch).mockImplementation(async (input) => {
      const path = String(input);
      if (path.endsWith('/screens')) return json({screens: ['home']});
      if (path.endsWith('/manifest')) return json({available: true, manifest: {expected_captures: 1, successful_captures: 1}});
      if (path.includes('/targets/')) return json({targets: [{text: 'Save', baseline_box: [10, 20, 110, 60]}]});
      if (path.includes('/labels/')) return json([
        {text: null, box: [0, 0, 20, 20]},
        {text: 'Save', box: [12, 22, 112, 62]},
      ]);
      return json([]);
    });

    render(<DatasetView dataset="demo" />);

    await waitFor(() => expect(screen.getByRole('button', {name: 'Save'})).toBeTruthy());
    expect(screen.getByRole('button', {name: 'Save'}).textContent).toContain('Save');
    expect(consoleError).not.toHaveBeenCalled();
  });
});

describe('CaptureHealth', () => {
  it('keeps warning details closed until opened and shows the count and caveat', () => {
    render(
      <CaptureHealth
        available
        manifest={{
          expected_captures: 3,
          successful_captures: 2,
          problems: ['settings capture is incomplete', 'help capture drifted'],
        }}
      />,
    );

    expect(screen.getByText('2 warnings')).toBeTruthy();
    expect(screen.getByText(/affected screens carry a caveat/)).toBeTruthy();
    const details = screen.getByText('Show warning details').closest('details');
    expect(details?.open).toBe(false);

    fireEvent.click(screen.getByText('Show warning details'));
    expect(details?.open).toBe(true);
    expect(screen.getByText('settings capture is incomplete')).toBeTruthy();
    expect(screen.getByText('help capture drifted')).toBeTruthy();
  });

  it('reports a complete manifest without a warning note', () => {
    render(
      <CaptureHealth
        available
        manifest={{expected_captures: 2, successful_captures: 2, problems: []}}
      />,
    );

    expect(screen.getByText('2/2 captures complete')).toBeTruthy();
    expect(screen.getByText('No drift or contamination warnings recorded.')).toBeTruthy();
    expect(screen.queryByText(/affected screens carry a caveat/)).toBeNull();
  });

  it('warns when the collection manifest is unavailable', () => {
    render(<CaptureHealth available={false} manifest={null} />);

    const warning = document.body.textContent || '';
    expect(warning).toContain('No collection_manifest.json for this dataset');
    expect(warning).toContain('capture completeness and content drift are unknown');
  });
});

describe('ModelsView', () => {
  it('persists models and rejects duplicates', async () => {
    vi.mocked(fetch).mockResolvedValue(json([]));
    render(<ModelsView />);
    fireEvent.change(screen.getByLabelText('Model id'), {target: {value: 'openai/test'}});
    fireEvent.click(screen.getByRole('button', {name: 'Add model'}));
    expect(JSON.parse(localStorage.getItem('agb_models') || '[]')).toEqual([{id: 'openai/test', coord_space: 'pixel'}]);
    fireEvent.change(screen.getByLabelText('Model id'), {target: {value: 'openai/test'}});
    fireEvent.click(screen.getByRole('button', {name: 'Add model'}));
    expect(screen.getByText('openai/test is already configured.')).toBeTruthy();
  });

  it('sets and clears provider session keys with stable payloads', async () => {
    let providers = [{provider: 'openai', env_vars: ['OPENAI_API_KEY'], configured: false, session_configured: false}];
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      const path = String(input);
      if (path === '/api/providers') return json(providers);
      if (path === '/api/keys' && init?.method === 'POST') {
        expect(JSON.parse(String(init.body))).toEqual({provider: 'openai', value: 'secret'});
        providers = [{...providers[0], configured: true, session_configured: true}];
        return json({ok: true});
      }
      if (path === '/api/keys/openai' && init?.method === 'DELETE') {
        providers = [{...providers[0], configured: false, session_configured: false}];
        return json({ok: true});
      }
      return json([]);
    });
    render(<ModelsView />);
    await waitFor(() => expect(screen.getByPlaceholderText('Paste key for this session')).toBeTruthy());
    fireEvent.change(screen.getByPlaceholderText('Paste key for this session'), {target: {value: 'secret'}});
    fireEvent.click(screen.getByRole('button', {name: 'Set'}));
    await waitFor(() => expect(screen.getByRole('button', {name: 'Clear'})).toBeTruthy());
    fireEvent.click(screen.getByRole('button', {name: 'Clear'}));
    await waitFor(() => expect(screen.getByText('Not configured')).toBeTruthy());
  });
});

describe('EvaluateView and CollectView', () => {
  it('loads evaluation preflight and submits the existing run payload', async () => {
    const calls: Array<{path: string; init?: RequestInit}> = [];
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      calls.push({path: String(input), init});
      if (String(input).includes('/preflight')) return json({expected_total: 4, already_done: 1, results_csv: 'results.csv'});
      if (String(input) === '/api/runs') return json({run_id: 'run-1'});
      if (String(input).startsWith('/api/runs/run-1')) return json({status: 'completed', lines: [], next_since: 0});
      return json([]);
    });
    render(<EvaluateView dataset="demo" models={[{id: 'openai/test', coord_space: 'pixel'}]} />);
    await waitFor(() => expect(screen.getByText(/4 queries planned|Resuming/)).toBeTruthy());
    fireEvent.submit(document.querySelector('#evaluate-form')!);
    await waitFor(() => expect(calls.some((x) => x.path === '/api/runs' && x.init?.method === 'POST')).toBe(true));
    const body = JSON.parse(String(calls.find((x) => x.path === '/api/runs')?.init?.body));
    expect(body).toMatchObject({dataset: 'demo', model: 'openai/test', trials: 1, pace_seconds: 0, coord_space: 'pixel', fresh: false});
  });

  it('validates collection input before posting', async () => {
    vi.mocked(fetch).mockImplementation(async (input) => String(input) === '/api/collect/screens' ? json({all_screens: ['home']}) : json([]));
    render(<CollectView />);
    await waitFor(() => expect(screen.getByText('home')).toBeTruthy());
    fireEvent.submit(document.querySelector('#collect-form')!);
    expect(screen.getByText('Enter a dataset name.')).toBeTruthy();
    expect(fetch).not.toHaveBeenCalledWith('/api/collect/runs', expect.anything());
  });
});

describe('Results, analysis, and run monitor', () => {
  it('filters results by prompt mode and opens/closes the misses drawer', async () => {
    vi.mocked(fetch).mockImplementation(async (input) => {
      if (String(input).endsWith('/results')) return json([
        {filename: 'a.csv', model: 'm-a', prompt_mode: 'vision', row_count: 2, statuses: {HIT: 1}, hits: 1, co_present_count: 2, accuracy: .5, baseline_accuracy: .6},
        {filename: 'b.csv', model: 'm-b', prompt_mode: 'tree', row_count: 2, statuses: {MISS: 1}, hits: 0, co_present_count: 2, accuracy: 0, baseline_accuracy: .6},
      ]);
      if (String(input).includes('/rows')) return json([{status: 'co_present', score: '0', target_text: 'Save', screen: 'home', profile: 'baseline'}]);
      return json([]);
    });
    render(<ResultsView dataset="demo" />);
    await waitFor(() => expect(document.querySelector('#results-table')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', {name: 'tree'}));
    expect(document.querySelector('#results-table')?.textContent).not.toContain('m-a');
    fireEvent.click(screen.getByRole('button', {name: /Misses/}));
    await waitFor(() => expect(screen.getByRole('dialog', {name: 'Miss inspector'})).toBeTruthy());
    fireEvent.click(screen.getByRole('button', {name: 'Close'}));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('loads analysis and posts the configured run request', async () => {
    const calls: Array<{path: string; init?: RequestInit}> = [];
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      calls.push({path: String(input), init});
      if (String(input).includes('/analysis?')) return json({available: false, reachability: [], pooled_permutation: [], mcnemar_per_model: [], direction_consistency: []});
      if (String(input) === '/api/analyze') return json({available: true, reachability: [{Sample: 'primary', Profile: 'high_contrast', Reachability: '0.8', CI_Low: '0.7', CI_High: '0.9', Targets_Present: '8', Targets_Total: '10'}], pooled_permutation: [], mcnemar_per_model: [], direction_consistency: []});
      return json([]);
    });
    render(<AnalyzeView dataset="demo" />);
    await waitFor(() => expect(screen.getByText(/No analysis has been run/)).toBeTruthy());
    fireEvent.submit(document.querySelector('#analyze-form')!);
    await waitFor(() => expect(calls.some((x) => x.path === '/api/analyze')).toBe(true));
    expect(JSON.parse(String(calls.find((x) => x.path === '/api/analyze')?.init?.body))).toMatchObject({dataset: 'demo', sample: 'all', mode: 'vision', permutations: 20000, seed: 0});
  });

  it('polls to terminal status and exposes cancellation', async () => {
    vi.mocked(fetch).mockImplementation(async (input) => String(input).includes('since=0') ? json({status: 'completed', lines: ['    [HIT] target'], next_since: 1}) : json({lines: [], next_since: 1}));
    const finished = vi.fn();
    render(<RunMonitor runId="run-1" expectedTotal={1} onFinish={finished} />);
    await waitFor(() => expect(screen.getByText('completed')).toBeTruthy());
    expect(screen.getByText(/1 \/ 1 queries/)).toBeTruthy();
    expect(finished).toHaveBeenCalledWith('completed');
  });
});
