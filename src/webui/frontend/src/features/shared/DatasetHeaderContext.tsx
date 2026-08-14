import { createContext, useContext, type ReactNode } from "react";
import type { Dataset } from "../../lib/api";

export type DatasetHeaderValue = {
  datasets: Dataset[];
  dataset: string;
  datasetsError?: string | null;
  onDatasetChange: (value: string) => void;
  loading: boolean;
};

const DatasetHeaderContext = createContext<DatasetHeaderValue | null>(null);

export function DatasetHeaderProvider({
  value,
  children,
}: {
  value: DatasetHeaderValue;
  children: ReactNode;
}) {
  return (
    <DatasetHeaderContext.Provider value={value}>
      {children}
    </DatasetHeaderContext.Provider>
  );
}

export function useDatasetHeader() {
  return useContext(DatasetHeaderContext);
}
