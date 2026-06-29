import React from 'react';
import { Link } from 'react-router-dom';
import humanizeDuration from 'humanize-duration';

import ErrorBoundary from 'components/ErrorBoundary/ErrorBoundary';

import { getAPIHost } from 'config/config';
import { PathEnum } from 'config/enums/routesEnum';

import {
  IGpuActiveRun,
  IGpuMachine,
  IGpuStatusResponse,
  IGpuStatusResponseOk,
} from 'services/api/gpu/gpuService';

import './GpuUsage.scss';

const REFRESH_INTERVAL_MS = 30_000;

function formatDuration(seconds: number): string {
  return humanizeDuration(seconds * 1000, {
    largest: 2,
    round: true,
    units: ['h', 'm', 's'],
  });
}

function GpuUsage(): React.FunctionComponentElement<React.ReactNode> {
  const [data, setData] = React.useState<
    IGpuStatusResponse | IGpuStatusResponseOk | null
  >(null);
  const [loading, setLoading] = React.useState(true);
  const [lastUpdated, setLastUpdated] = React.useState<Date | null>(null);
  const mountedRef = React.useRef(true);

  React.useEffect(() => {
    mountedRef.current = true;

    function fetchData() {
      fetch(`${getAPIHost()}/gpu/`, {
        headers: { 'Content-Type': 'application/json' },
      })
        .then((res) => res.json())
        .then((result: any) => {
          if (!mountedRef.current) return;
          setData(result);
          setLastUpdated(new Date());
          setLoading(false);
        })
        .catch(() => {
          if (!mountedRef.current) return;
          setLoading(false);
        });
    }

    fetchData();
    const interval = setInterval(fetchData, REFRESH_INTERVAL_MS);

    return () => {
      mountedRef.current = false;
      clearInterval(interval);
    };
  }, []);

  if (loading) {
    return (
      <div className='GpuUsage'>
        <div className='GpuUsage__loader'>Loading GPU status…</div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className='GpuUsage'>
        <div className='GpuUsage__errorBanner'>
          <span>⚠</span>
          Failed to load GPU status.
        </div>
      </div>
    );
  }

  if (!data.tailscale_available) {
    return (
      <div className='GpuUsage'>
        <div className='GpuUsage__header'>
          <span className='GpuUsage__header__title'>GPU Usage</span>
        </div>
        <div className='GpuUsage__errorBanner'>
          <span>⚠</span>
          tailscale is not available on this server — cannot retrieve GPU list
        </div>
      </div>
    );
  }

  const okData = data as IGpuStatusResponseOk;
  const busyHostnames = new Set(
    okData.active_runs.map((r) => r.hostname).filter(Boolean),
  );
  const freeGpus: IGpuMachine[] = okData.machines.filter(
    (m) => !busyHostnames.has(m.hostname),
  );
  const activeRuns: IGpuActiveRun[] = okData.active_runs;

  return (
    <ErrorBoundary>
      <div className='GpuUsage'>
        <div className='GpuUsage__header'>
          <span className='GpuUsage__header__title'>GPU Usage</span>
          {lastUpdated && (
            <span className='GpuUsage__header__refresh'>
              Updated {lastUpdated.toLocaleTimeString()} · refreshes every 30s
            </span>
          )}
        </div>

        <div className='GpuUsage__section'>
          <div className='GpuUsage__section__label'>
            Free GPUs
            <span className='GpuUsage__section__count'>{freeGpus.length}</span>
          </div>
          {freeGpus.length === 0 ? (
            <p className='GpuUsage__emptyChips'>All GPU machines are in use.</p>
          ) : (
            <div className='GpuUsage__chips'>
              {freeGpus.map((m) => (
                <div key={m.hostname} className='GpuUsage__chip'>
                  <span className='GpuUsage__chip__dot' />
                  {m.hostname}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className='GpuUsage__section'>
          <div className='GpuUsage__section__label'>
            In Use
            <span className='GpuUsage__section__count'>
              {activeRuns.length}
            </span>
          </div>
          {activeRuns.length === 0 ? (
            <p className='GpuUsage__emptyChips'>No active runs.</p>
          ) : (
            <>
              <div className='GpuUsage__tableWrapper'>
                <table className='GpuUsage__table'>
                  <thead>
                    <tr>
                      <th>GPU</th>
                      <th>User</th>
                      <th>Run Name</th>
                      <th>Duration</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {activeRuns.map((run) => (
                      <tr key={run.hash}>
                        <td className='mono'>
                          {run.hostname ?? <span className='dim'>Unknown</span>}
                        </td>
                        <td>
                          {run.tags.length > 0 ? (
                            run.tags[0]
                          ) : (
                            <span className='dim'>—</span>
                          )}
                        </td>
                        <td>
                          <Link
                            className='GpuUsage__runLink'
                            to={PathEnum.Run_Detail.replace(
                              ':runHash',
                              run.hash,
                            )}
                          >
                            {run.name ?? run.hash.slice(0, 8)}
                          </Link>
                        </td>
                        <td className='mono'>{formatDuration(run.duration)}</td>
                        <td>
                          <span className='GpuUsage__activePill'>
                            <span className='GpuUsage__activePill__dot' />
                            active
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className='GpuUsage__hint'>
                GPU column shows "Unknown" when the run has no{' '}
                <code>run["hostname"]</code> param set.
              </p>
            </>
          )}
        </div>
      </div>
    </ErrorBoundary>
  );
}

export default GpuUsage;
