export interface SavedView<T = unknown> { name: string; config: T; savedAt: number }
const KEY = "agb.savedViews.v1";
const read = <T,>(): SavedView<T>[] => { try { const v = JSON.parse(localStorage.getItem(KEY) || "[]"); return Array.isArray(v) ? v : []; } catch { return []; } };
export const listViews = <T,>() => read<T>().sort((a, b) => b.savedAt - a.savedAt);
export function saveView<T>(name: string, config: T) { const views = read<T>().filter((v) => v.name !== name); views.push({ name, config, savedAt: Date.now() }); try { localStorage.setItem(KEY, JSON.stringify(views)); } catch { /* storage is optional */ } return listViews<T>(); }
export function deleteView(name: string) { const views = read().filter((v) => v.name !== name); try { localStorage.setItem(KEY, JSON.stringify(views)); } catch { /* storage is optional */ } return listViews(); }
