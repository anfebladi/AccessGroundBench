import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it} from 'vitest';
import {StageHeader} from '../../src/features/shared/StageHeader';
import {TABS, type Tab} from '../../src/app/navigation';

afterEach(() => cleanup());

const EYEBROWS: Record<Tab, string> = {
  dataset: 'Set up',
  models: 'Set up',
  evaluate: 'Run',
  collect: 'Run',
  compare: 'Compare',
  results: 'Read',
  analyze: 'Read',
};

describe('stage header', () => {
  it.each(TABS)('labels the %s stage with its workflow phase', (stage) => {
    const title = stage[0].toUpperCase() + stage.slice(1);
    const {container} = render(
      <StageHeader stage={stage} title={title}>
        Stage description.
      </StageHeader>,
    );

    const heading = screen.getByRole('heading', {level: 2, name: title});
    expect(heading.id).toBe(`head-${stage}`);
    const head = container.querySelector('.view-head');
    expect(head).toBeTruthy();
    expect(head!.firstElementChild!.textContent).toBe(EYEBROWS[stage]);
    expect(head!.textContent).toContain('Stage description.');
  });

  it('renders inline description markup', () => {
    const {container} = render(
      <StageHeader stage="collect" title="Collect">
        Writes to <code>collections/&lt;name&gt;/</code> only.
      </StageHeader>,
    );

    expect(container.querySelector('code')!.textContent).toBe('collections/<name>/');
  });

  it('leaves the readiness cue out of the stage header', () => {
    render(
      <StageHeader stage="analyze" title="Analyze">
        Reachability, pooled permutation tests, and per-model tests.
      </StageHeader>,
    );

    expect(screen.queryByRole('status')).toBeNull();
  });
});
