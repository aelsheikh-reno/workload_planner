import { useEffect, useMemo, useState } from "react";

import { requestJson } from "./api";

export function useRouteData(path, { query = {}, enabled = true } = {}) {
  const [reloadToken, setReloadToken] = useState(0);
  const [state, setState] = useState({
    data: null,
    error: null,
    loading: enabled,
  });

  const queryKey = useMemo(() => JSON.stringify(query || {}), [query]);

  useEffect(() => {
    if (!enabled) {
      setState({ data: null, error: null, loading: false });
      return undefined;
    }

    const controller = new AbortController();
    setState((current) => ({
      data: current.data,
      error: null,
      loading: true,
    }));

    requestJson(path, {
      query,
      signal: controller.signal,
    })
      .then((data) => {
        setState({ data, error: null, loading: false });
      })
      .catch((error) => {
        if (controller.signal.aborted) {
          return;
        }
        setState((current) => ({
          data: current.data,
          error,
          loading: false,
        }));
      });

    return () => controller.abort();
  }, [enabled, path, queryKey, reloadToken]);

  return {
    ...state,
    reload() {
      setReloadToken((value) => value + 1);
    },
  };
}
