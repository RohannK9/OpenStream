export {};

declare global {
  interface Window {
    __OPENSTREAM_CONFIG__?: {
      apiBaseUrl?: string;
      grafanaUrl?: string;
      prometheusUrl?: string;
    };
  }
}

