export interface SavedView<T = unknown> { name: string; config: T; savedAt: number }
const KEY = "agb.savedViews.v1";
const read = <T,>(): SavedView<T>[] => {
  try {
    const value = JSON.parse(localStorage.getItem(KEY) || "[]");
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
};
export const listViews = <T,>() => read<T>().sort((a, b) => b.savedAt - a.savedAt);
export function saveView<T>(name: string, config: T) {
  const views = read<T>().filter((view) => view.name !== name);
  views.push({ name, config, savedAt: Date.now() });
  try {
    localStorage.setItem(KEY, JSON.stringify(views));
  } catch {
    // Saved views are optional when storage is unavailable.
  }
  return listViews<T>();
}

export function deleteView(name: string) {
  const views = read().filter((view) => view.name !== name);
  try {
    localStorage.setItem(KEY, JSON.stringify(views));
  } catch {
    // Saved views are optional when storage is unavailable.
  }
  return listViews();
}
