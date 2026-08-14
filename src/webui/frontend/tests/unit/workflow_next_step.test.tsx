import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it} from 'vitest';
import {AppShell} from '../../src/components/shell/AppShell';
import type {Dataset, Model, Provider} from '../../src/lib/api';
import type {PreflightSummary} from '../../src/lib/types';

const dataset: Dataset = {name: 'demo', screen_count: 2, image_count: 4, is_archived: false};
const provider: Provider = {
  name: 'openai',
  env_vars: [],
  configured: true,
  env_configured: false,
  session_configured: false,
};
const model: Model = {id: 'openai/test', coord_space: 'pixel'};

function renderShell(overrides: Partial<React.ComponentProps<typeof AppShell>> = {}) {
  return render(
    <AppShell
      route="dataset"
      datasets={[dataset]}
      dataset="demo"
      models={[]}
      providers={[provider]}
      evaluate={{text: 'Select a model', tone: 'muted'}}
      compareCount={0}
      resultsCount={0}
      onDatasetChange={() => undefined}
      onPalette={() => undefined}
      {...overrides}
    >
      <div data-testid="view-content">View content</div>
    </AppShell>,
  );
}

beforeEach(() => localStorage.clear());
afterEach(() => cleanup());

describe('workflow next-step cue', () => {
  it.each([
    ['dataset without a selection', {route: 'dataset' as const, dataset: ''}, 'Choose a dataset to begin.'],
    ['dataset with a selection', {route: 'dataset' as const, dataset: 'demo'}, 'Review your capture set before running a workflow.'],
    ['models without configured models', {route: 'models' as const, models: []}, 'Configure a model before evaluating.'],
    ['models with a configured model', {route: 'models' as const, models: [model]}, 'Your model roster is ready for an evaluation.'],
    ['comparison without runs', {route: 'compare' as const, compareCount: 0}, 'Collect results before comparing models.'],
    ['comparison with selected runs', {route: 'compare' as const, compareCount: 2}, 'Compare selected model runs side by side.'],
    ['results without runs', {route: 'results' as const, resultsCount: 0}, 'Run an evaluation to populate results.'],
    ['results with runs', {route: 'results' as const, resultsCount: 1}, 'Inspect accuracy and evidence from your latest runs.'],
    ['analysis with results', {route: 'analyze' as const, resultsCount: 1}, 'Turn result files into statistical evidence.'],
  ])('describes the %s state from client data', (_label, props, expected) => {
    renderShell(props);

    const cue = screen.getByRole('status');
    expect(cue.id).toBe('workflow-next-step');
    expect(cue.getAttribute('aria-live')).toBe('polite');
    expect(cue.textContent).toContain(expected);
  });

  it('does not block the active view with an interactive control', () => {
    renderShell({route: 'results', resultsCount: 1});

    expect(screen.getByTestId('view-content')).toBeTruthy();
    const cue = screen.getByRole('status');
    expect(cue.querySelector('button, a, input, select, textarea')).toBeNull();
  });

  it('uses the evaluate preflight text when available', () => {
    const evaluate: PreflightSummary = {text: '2 captures are ready', tone: 'info'};
    renderShell({route: 'evaluate', evaluate});

    expect(screen.getByRole('status').textContent).toContain('2 captures are ready');
  });
});
