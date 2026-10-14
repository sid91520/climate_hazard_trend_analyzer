import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { TooltipProps } from 'recharts'
import { describeTrend } from '@/format'
import { useChartColors } from '@/hooks/useChartColors'
import type { MetricKey, MetricTrend, YearlyMetrics } from '@/types'

interface Props {
  title: string
  metric: MetricKey
  unit: string // shown on the y-axis and in tooltips, e.g. "days"
  yearly: YearlyMetrics[]
  trend: MetricTrend
}

interface Point {
  year: number
  value: number | null
  rolling: number | null
  trend: number | null
}

/** Yearly bars + 5-year rolling mean + linear trend line, for one metric. */
export function MetricChart({ title, metric, unit, yearly, trend }: Props) {
  const colors = useChartColors()
  const linear = trend.linear
  const data: Point[] = yearly.map((row) => ({
    year: row.year,
    value: row[metric],
    rolling: row[`${metric}_rolling`],
    // The backend sends slope + intercept; the line is just y = intercept + slope × year.
    trend: linear ? linear.intercept + (linear.slope_per_decade / 10) * row.year : null,
  }))

  return (
    <figure className="card chart-card">
      <figcaption>
        <h3>{title}</h3>
        <p className="muted">{describeTrend(trend, unit)}</p>
      </figcaption>
      <ResponsiveContainer width="100%" height={260}>
        <ComposedChart data={data} margin={{ top: 4, right: 12, bottom: 20, left: 4 }}>
          <CartesianGrid vertical={false} stroke={colors.grid} />
          <XAxis
            dataKey="year"
            tick={{ fill: colors.axis, fontSize: 12 }}
            stroke={colors.grid}
            minTickGap={16}
            label={{ value: 'Year', position: 'insideBottom', offset: -12, fill: colors.axis, fontSize: 12 }}
          />
          <YAxis
            // Start at 0 and clip the trend line there: these metrics can't be negative.
            domain={[0, 'auto']}
            allowDataOverflow
            tick={{ fill: colors.axis, fontSize: 12 }}
            stroke={colors.grid}
            width={48}
            label={{ value: unit, angle: -90, position: 'insideLeft', fill: colors.axis, fontSize: 12, style: { textAnchor: 'middle' } }}
          />
          <Tooltip content={<ChartTooltip unit={unit} />} cursor={{ fill: colors.grid, opacity: 0.5 }} />
          <Legend verticalAlign="top" height={28} iconSize={10} wrapperStyle={{ fontSize: 12, color: colors.axis }} />
          <Bar dataKey="value" name="Yearly value" fill={colors.bar} radius={[4, 4, 0, 0]} maxBarSize={24} />
          <Line dataKey="rolling" name="5-year average" stroke={colors.rolling} strokeWidth={2} dot={false} connectNulls={false} />
          <Line dataKey="trend" name="Linear trend" stroke={colors.trend} strokeWidth={2} strokeDasharray="6 4" dot={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </figure>
  )
}

function ChartTooltip({ active, payload, label, unit }: TooltipProps<number, string> & { unit: string }) {
  if (!active || !payload?.length) return null
  const point = payload[0].payload as Point
  const fmt = (v: number | null) => (v === null ? '–' : `${v.toFixed(1)} ${unit}`)
  return (
    <div className="chart-tooltip">
      <strong>{label}</strong>
      <div>Value: {point.value === null ? 'no heatwave' : fmt(point.value)}</div>
      <div>5-year average: {fmt(point.rolling)}</div>
      <div>Trend line: {fmt(point.trend)}</div>
    </div>
  )
}
