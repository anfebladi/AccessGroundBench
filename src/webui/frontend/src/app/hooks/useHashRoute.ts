import { useCallback, useEffect, useState } from "react";
import { normalizeTab, type Tab } from "../navigation";

export function useHashRoute(): [Tab, (tab: Tab) => void] {
  const [route, setRoute] = useState<Tab>(() =>
    normalizeTab(window.location.hash.slice(1)),
  );

  const go = useCallback((tab: Tab) => {
    window.location.hash = `#${tab}`;
  }, []);

  useEffect(() => {
    const onHashChange = () => {
      setRoute(normalizeTab(window.location.hash.slice(1)));
    };

    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    window.scrollTo?.({ top: 0 });
  }, [route]);

  return [route, go];
}
