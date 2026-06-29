import { IApiRequest } from 'types/services/services';

import API from '../api';
import ENDPOINTS from '../endpoints';

export interface IGpuMachine {
  hostname: string;
  ip: string | null;
}

export interface IGpuActiveRun {
  hash: string;
  name: string | null;
  experiment: string | null;
  creation_time: number;
  duration: number;
  hostname: string | null;
  tags: string[];
}

export interface IGpuStatusResponse {
  tailscale_available: false;
}

export interface IGpuStatusResponseOk {
  tailscale_available: true;
  machines: IGpuMachine[];
  active_runs: IGpuActiveRun[];
}

function getGpuStatus(): IApiRequest<
  IGpuStatusResponse | IGpuStatusResponseOk
> {
  return API.get(`${ENDPOINTS.GPU.BASE}/`);
}

const gpuService = {
  getGpuStatus,
};

export default gpuService;
