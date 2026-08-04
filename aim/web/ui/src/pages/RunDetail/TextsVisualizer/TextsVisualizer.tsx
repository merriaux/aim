import React from 'react';

import ErrorBoundary from 'components/ErrorBoundary/ErrorBoundary';
import DataList from 'components/kit/DataList';
import { Button, Icon } from 'components/kit';

import { ITableRef } from 'types/components/Table/Table';

import { downloadLink } from 'utils/helper';

import { ITextsVisualizerProps } from '../types';

import './TextsVisualizer.scss';

const DEFAULT_TEXT_FILE_NAME = 'text.txt';

function sanitizeFileName(fileName?: string): string {
  const sanitizedName = (fileName || 'text')
    .trim()
    .replace(/[\\/:*?"<>|]+/g, '_');
  const normalizedName = sanitizedName || 'text';

  return normalizedName.toLowerCase().endsWith('.txt')
    ? normalizedName
    : `${normalizedName}.txt`;
}

function TextsVisualizer(
  props: ITextsVisualizerProps | any,
): React.FunctionComponentElement<React.ReactNode> {
  const tableRef = React.useRef<ITableRef>(null);
  const { activeTraceContext, data, isLoading } = props;
  const textsData = React.useMemo(
    () => data?.processedValues || [],
    [data?.processedValues],
  );

  const onDownloadText = React.useCallback(() => {
    const firstTextItem = textsData[0];
    const textName = firstTextItem?.name || data?.name || activeTraceContext;
    const fileNameParts = [
      textName || DEFAULT_TEXT_FILE_NAME,
      firstTextItem?.step !== undefined ? `step-${firstTextItem.step}` : null,
      firstTextItem?.index !== undefined
        ? `index-${firstTextItem.index}`
        : null,
    ].filter(Boolean);
    const fileName = sanitizeFileName(
      fileNameParts.join('_') || DEFAULT_TEXT_FILE_NAME,
    );
    const content = textsData.map((item: any) => item.text).join('\n\n');
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);

    downloadLink(url, fileName);
    URL.revokeObjectURL(url);
  }, [activeTraceContext, data?.name, textsData]);

  const tableColumns = [
    {
      dataKey: 'step',
      key: 'step',
      title: 'Step',
      width: 100,
    },
    {
      dataKey: 'index',
      key: 'index',
      title: 'Index',
      width: 100,
    },
    {
      dataKey: 'text',
      key: 'text',
      title: 'Text',
      width: 0,
      flexGrow: 1,
      // TODO: replace with a wrapper component for all types of texts visualization
      // eslint-disable-next-line react/display-name
      cellRenderer: ({ cellData }: any) => (
        <div className='ScrollBar__hidden TextsVisualizer__textCell'>
          <pre>{cellData}</pre>
        </div>
      ),
    },
  ];

  return (
    <ErrorBoundary>
      <div className='TextsVisualizer'>
        <DataList
          tableRef={tableRef}
          tableData={textsData}
          tableColumns={tableColumns}
          isLoading={isLoading}
          searchableKeys={['text']}
          toolbarItems={[
            <Button
              key='download-text'
              className='TextsVisualizer__downloadButton'
              title='Download text'
              withOnlyIcon
              size='small'
              disabled={!textsData.length}
              onClick={onDownloadText}
            >
              <Icon name='download' />
            </Button>,
          ]}
        />
      </div>
    </ErrorBoundary>
  );
}

TextsVisualizer.displayName = 'TextsVisualizer';

export default React.memo<ITextsVisualizerProps>(TextsVisualizer);
