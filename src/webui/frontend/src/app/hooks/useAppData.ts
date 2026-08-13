import { useCallback, useEffect, useState } from "react";
import { api, type Dataset, type Provider } from "../../lib/api";

interface DatasetData {
  screens: string[];
  resultCount: number;
}

async function fetchDatasetData(
  name: string,
  signal: AbortSignal,
): Promise<DatasetData> {
  const [screenResult, result] = await Promise.allSettled([
    api<{ screens: string[] }>(
      `/api/datasets/${encodeURIComponent(name)}/screens`,
      { signal },
    ),
    api<Array<{ filename?: string }>>(
      `/api/datasets/${encodeURIComponent(name)}/results`,
      { signal },
    ),
  ]);

  return {
    screens:
      screenResult.status === "fulfilled" ? screenResult.value.screens ?? [] : [],
    resultCount: result.status === "fulfilled" ? result.value.length : 0,
  };
}

export function useAppData() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [dataset, setDataset] = useState("");
  const [screens, setScreens] = useState<string[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [resultCount, setResultCount] = useState(0);
  const [compareCount, setCompareCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [datasetLoading, setDatasetLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    const [datasetList, providerList] = await Promise.allSettled([
      api<Dataset[]>("/api/datasets"),
      api<Provider[]>("/api/providers"),
    ]);

    if (datasetList.status === "fulfilled") {
      setDatasets(datasetList.value);
      setDataset((current) =>
        datasetList.value.some((item) => item.name === current)
          ? current
          : datasetList.value[0]?.name ?? "",
      );
    }

    if (providerList.status === "fulfilled") {
      setProviders(providerList.value);
    }
    setLoading(false);
  }, []);

  const refreshDatasetData = useCallback(async (name: string) => {
    const controller = new AbortController();
    setDatasetLoading(true);

    try {
      const next = await fetchDatasetData(name, controller.signal);
      setScreens(next.screens);
      setResultCount(next.resultCount);
    } finally {
      controller.abort();
      setDatasetLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!dataset) {
      setScreens([]);
      setResultCount(0);
      setCompareCount(0);
      return;
    }

    void refreshDatasetData(dataset);
  }, [dataset, refreshDatasetData]);

  return {
    datasets,
    dataset,
    setDataset,
    screens,
    providers,
    setProviders,
    resultCount,
    setResultCount,
    compareCount,
    setCompareCount,
    refresh,
    refreshDatasetData,
    loading,
    datasetLoading,
  };
}
