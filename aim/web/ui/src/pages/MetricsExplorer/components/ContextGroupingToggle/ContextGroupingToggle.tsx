import * as React from 'react';
import classNames from 'classnames';

import { Tooltip } from '@material-ui/core';

import ErrorBoundary from 'components/ErrorBoundary';
import { Button, Icon, Text } from 'components/kit';

import { IBaseComponentProps } from 'modules/BaseExplorer/types';
import { GroupType, Order } from 'modules/core/pipeline';

const GROUPING_OPTIONS = [
  {
    field: 'metric.context.subset',
    label: 'Subset',
    contextKey: 'subset',
  },
  {
    field: 'metric.context.category',
    label: 'Category',
    contextKey: 'category',
  },
];

interface IContextGroupingToggleProps extends IBaseComponentProps {
  visualizationName: string;
}

function ContextGroupingToggle(props: IContextGroupingToggleProps) {
  const {
    engine: { useStore, pipeline, groupings },
  } = props;

  const availableModifiers = useStore(pipeline.additionalDataSelector);
  const currentValues = useStore(groupings.currentValuesSelector);

  const rowGrouping = currentValues?.[GroupType.ROW];
  const currentField = rowGrouping?.fields?.[0];
  const currentOption = GROUPING_OPTIONS.find(
    (option) => option.field === currentField,
  );

  const availableOptions = React.useMemo(() => {
    const modifiers = availableModifiers?.modifiers ?? [];

    if (modifiers.length === 0) {
      return GROUPING_OPTIONS;
    }

    return GROUPING_OPTIONS.filter((option) =>
      modifiers.includes(option.field),
    );
  }, [availableModifiers?.modifiers]);

  const nextOption = React.useMemo(() => {
    if (availableOptions.length === 0) {
      return null;
    }

    const currentIndex = availableOptions.findIndex(
      (option) => option.field === currentField,
    );

    return availableOptions[(currentIndex + 1) % availableOptions.length];
  }, [availableOptions, currentField]);

  const isDisabled =
    !nextOption ||
    !currentValues?.[GroupType.ROW] ||
    nextOption.field === currentField;
  const activeLabel = currentOption?.label ?? 'Custom';

  const onToggleGrouping = React.useCallback(() => {
    if (isDisabled || !nextOption) {
      return;
    }

    const nextValues = {
      ...currentValues,
      [GroupType.ROW]: {
        fields: [nextOption.field],
        orders: [rowGrouping?.orders?.[0] ?? Order.ASC],
      },
    };

    groupings.update(nextValues);
    pipeline.group(nextValues);
  }, [currentValues, groupings, isDisabled, nextOption, pipeline, rowGrouping]);

  return (
    <ErrorBoundary>
      <Tooltip
        title={
          !isDisabled && nextOption
            ? `Group figures by context:${nextOption.contextKey}`
            : 'No alternate context grouping available'
        }
      >
        <div>
          <Button
            size='xSmall'
            className={classNames('Control__anchor', {
              active: !!currentOption,
              outlined: currentOption?.field === 'metric.context.category',
              disabled: isDisabled,
            })}
            onClick={onToggleGrouping}
          >
            <Icon
              name='image-group'
              className={classNames('Control__anchor__icon', {
                active: !!currentOption,
              })}
            />
            <Text className='Control__anchor__label'>Group: {activeLabel}</Text>
          </Button>
        </div>
      </Tooltip>
    </ErrorBoundary>
  );
}

ContextGroupingToggle.displayName = 'ContextGroupingToggle';

export default React.memo(ContextGroupingToggle);
