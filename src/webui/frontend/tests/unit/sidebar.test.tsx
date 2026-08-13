import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {AppShell} from '../../src/components/shell/AppShell';
import {Sidebar} from '../../src/components/shell/Sidebar';
import type {Dataset, Model, Provider} from '../../src/lib/api';
import type {PreflightSummary} from '../../src/lib/types';

const dataset: Dataset = {name: 'demo', screen_count: 2, image_count: 4, is_archived: false};
const models: Model[] = [];
const providers: Provider[] = [];
const evaluate: PreflightSummary = {text: 'ready', tone: 'muted'};

function sidebarProps(overrides: Partial<React.ComponentProps<typeof Sidebar>> = {}) {
  return {
    route: 'dataset' as const,
    datasets: [dataset],
    dataset: 'demo',
    models,
    providers,
    evaluate,
    compareCount: 0,
    resultsCount: 0,
    ...overrides,
  };
}

function shellProps(overrides: Partial<React.ComponentProps<typeof AppShell>> = {}) {
  return {
    ...sidebarProps(),
    onDatasetChange: vi.fn(),
    onPalette: vi.fn(),
    children: <div data-testid="content">content</div>,
    ...overrides,
  };
}

beforeEach(() => localStorage.clear());
afterEach(() => cleanup());

describe('desktop workflow rail', () => {
  it('toggles the desktop rail and preserves route hooks and accessible names when collapsed', () => {
    const onToggleCollapsed = vi.fn();
    const {rerender} = render(<Sidebar {...sidebarProps({onToggleCollapsed})} />);
    const rail = screen.getByRole('navigation', {name: 'Workflow'});
    const toggle = screen.getByRole('button', {name: 'Collapse workflow sidebar'});
    expect(toggle.className).toContain('collapseToggle');
    expect(toggle.querySelector('svg path')?.getAttribute('d')).toBe(
      'M4 7h16M4 12h16M4 17h16',
    );

    fireEvent.click(toggle);
    expect(onToggleCollapsed).toHaveBeenCalledTimes(1);

    rerender(<Sidebar {...sidebarProps({collapsed: true, onToggleCollapsed})} />);
    const expandToggle = screen.getByRole('button', {name: 'Expand workflow sidebar'});
    expect(expandToggle.className).toContain('collapseToggle');
    expect(expandToggle.querySelector('svg path')?.getAttribute('d')).toBe(
      'M4 7h16M4 12h16M4 17h16',
    );
    expect(rail.className).toContain('railCollapsed');
    for (const tab of ['dataset', 'models', 'evaluate', 'collect', 'compare', 'results', 'analyze']) {
      const link = document.querySelector(`a[data-tab="${tab}"]`);
      expect(link).not.toBeNull();
      expect(link?.getAttribute('aria-label')).toBeTruthy();
      expect(link?.getAttribute('title')).toBeTruthy();
    }
    expect(document.querySelector('a[data-tab="dataset"]')?.getAttribute('aria-current')).toBe('page');
  });

  it('restores the persisted collapsed preference in AppShell without collapsing mobile navigation', async () => {
    localStorage.setItem('agb.sidebar.collapsed', '1');
    render(<AppShell {...shellProps()} />);

    await waitFor(() => expect(screen.getByRole('button', {name: 'Expand workflow sidebar'})).toBeTruthy());
    const desktopRail = document.getElementById('rail');
    expect(desktopRail?.className).toContain('railCollapsed');

    fireEvent.click(screen.getByRole('button', {name: 'Open workflow menu'}));
    const mobileRail = await screen.findByRole('navigation', {name: 'Workflow'});
    expect(mobileRail.id).toBe('mobile-rail');
    expect(within(mobileRail).queryByRole('button', {name: /sidebar/i})).toBeNull();
    expect(within(mobileRail).getByText('Dataset')).toBeTruthy();
  });

  it('renders compact skeleton chips while shared shell metadata is loading', () => {
    render(<Sidebar {...sidebarProps({loading: true})} />);
    expect(document.querySelectorAll('.rail-chip-skeleton').length).toBe(4);
    expect(screen.getByRole('link', {name: 'Dataset'})).toBeTruthy();
  });
});
