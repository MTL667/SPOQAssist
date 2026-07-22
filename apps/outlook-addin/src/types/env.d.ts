declare namespace NodeJS {
  interface ProcessEnv {
    HUB_BASE_URL?: string;
  }
}

declare const process: {
  env: NodeJS.ProcessEnv;
};
